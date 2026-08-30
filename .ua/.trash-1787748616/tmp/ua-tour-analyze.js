#!/usr/bin/env node
"use strict";
/* Phase 1 graph-topology analyzer for the tour-builder agent.
 * Usage: node ua-tour-analyze.js <input.json> <output.json>
 * Exits 0 on success, 1 on fatal error (message to stderr).
 */
const fs = require("fs");

function main() {
  const [, , inputPath, outputPath] = process.argv;
  if (!inputPath || !outputPath) {
    console.error("usage: ua-tour-analyze.js <input.json> <output.json>");
    process.exit(1);
  }

  let input;
  try {
    input = JSON.parse(fs.readFileSync(inputPath, "utf8"));
  } catch (e) {
    console.error("fatal: cannot read/parse input: " + e.message);
    process.exit(1);
  }

  const nodes = Array.isArray(input.nodes) ? input.nodes : [];
  const edges = Array.isArray(input.edges) ? input.edges : [];
  const layers = Array.isArray(input.layers) ? input.layers : [];
  const nodeIds = new Set(nodes.map((n) => n.id));

  // ---- adjacency -------------------------------------------------------
  const fanIn = new Map(); // id -> count of incoming edges
  const fanOut = new Map();
  const succ = new Map(); // id -> [{target,type}]
  const pred = new Map();
  const undirected = new Map(); // id -> Set(neighbours) over dependency edges
  const DEP_TYPES = new Set(["imports", "calls", "depends_on"]);

  for (const n of nodes) {
    fanIn.set(n.id, 0);
    fanOut.set(n.id, 0);
    succ.set(n.id, []);
    pred.set(n.id, []);
    undirected.set(n.id, new Set());
  }
  for (const e of edges) {
    if (!nodeIds.has(e.source) || !nodeIds.has(e.target)) continue;
    fanOut.set(e.source, fanOut.get(e.source) + 1);
    fanIn.set(e.target, fanIn.get(e.target) + 1);
    succ.get(e.source).push({ target: e.target, type: e.type });
    pred.get(e.target).push({ source: e.source, type: e.type });
    if (DEP_TYPES.has(e.type)) {
      undirected.get(e.source).add(e.target);
      undirected.get(e.target).add(e.source);
    }
  }

  // ---- A. fan-in ranking -----------------------------------------------
  const fanInRanking = [...fanIn.entries()]
    .map(([id, v]) => ({ id, fanIn: v, name: nameOf(id) }))
    .sort((a, b) => b.fanIn - a.fanIn || a.id.localeCompare(b.id))
    .slice(0, 20);

  // ---- B. fan-out ranking ----------------------------------------------
  const fanOutRanking = [...fanOut.entries()]
    .map(([id, v]) => ({ id, fanOut: v, name: nameOf(id) }))
    .sort((a, b) => b.fanOut - a.fanOut || a.id.localeCompare(b.id))
    .slice(0, 20);

  // ---- C. entry-point candidates ----------------------------------------
  const N = nodes.length;
  const foSorted = [...fanOut.values()].sort((a, b) => b - a);
  const fiSortedAsc = [...fanIn.values()].sort((a, b) => a - b);
  const hiFanOutCut = foSorted[Math.max(0, Math.ceil(0.1 * N) - 1)] ?? Infinity;
  const loFanInCut = fiSortedAsc[Math.max(0, Math.floor(0.25 * N) - 1)] ?? -Infinity;

  const ENTRY_FILENAMES = new Set([
    "index.ts", "index.js", "main.ts", "main.js", "app.ts", "app.js",
    "server.ts", "server.js", "mod.rs", "main.go", "main.py", "main.rs",
    "manage.py", "app.py", "wsgi.py", "asgi.py", "run.py", "__main__.py",
    "Application.java", "Main.java", "Program.cs", "config.ru", "index.php",
    "App.swift", "Application.kt", "main.cpp", "main.c",
  ]);

  const candidates = [];
  for (const n of nodes) {
    let score = 0;
    const fileName = n.name || "";
    const fp = (n.filePath || "").replace(/^\.\//, "");
    const depth = fp.split("/").length; // 1 == project root
    if (n.type === "document") {
      if (/^readme\.md$/i.test(fileName) && depth === 1) score += 5;
      else if (/\.md$/i.test(fileName) && depth === 1) score += 2;
    } else {
      if (ENTRY_FILENAMES.has(fileName)) score += 3;
      if (depth <= 2) score += 1;
      if (fanOut.get(n.id) >= hiFanOutCut) score += 1;
      if (fanIn.get(n.id) <= loFanInCut) score += 1;
      if (score === 0 && !isCodeLike(n)) continue; // skip non-code noise unless scored
    }
    if (score > 0) {
      candidates.push({ id: n.id, score, name: fileName, summary: n.summary || "" });
    }
  }
  candidates.sort((a, b) => b.score - a.score || a.id.localeCompare(b.id));
  const entryPointCandidates = candidates.slice(0, 5);

  // ---- D. BFS from top CODE entry point ---------------------------------
  let bfsStart = null;
  for (const c of candidates) {
    if (c.id.startsWith("file:")) { bfsStart = c.id; break; }
  }
  const order = [];
  const depthMap = {};
  if (bfsStart) {
    const visited = new Set([bfsStart]);
    let frontier = [bfsStart];
    let d = 0;
    while (frontier.length) {
      const next = [];
      for (const id of frontier) {
        order.push(id);
        depthMap[id] = d;
        for (const { target, type } of succ.get(id) || []) {
          // follow dependency edges (imports/calls, plus depends_on which
          // encodes module-level dependency links in this graph)
          if (!DEP_TYPES.has(type)) continue;
          if (!visited.has(target)) { visited.add(target); next.push(target); }
        }
      }
      next.sort((a, b) => a.localeCompare(b));
      frontier = next;
      d++;
    }
  }
  const byDepth = {};
  for (const [id, d] of Object.entries(depthMap)) {
    (byDepth[String(d)] ||= []).push(id);
  }
  const bfsTraversal = { startNode: bfsStart, order, depthMap, byDepth };

  // ---- E. non-code inventory --------------------------------------------
  const DOC_DOC_TYPES = new Set(["document"]);
  const INFRA_TYPES = new Set(["service", "pipeline", "resource"]);
  const DATA_TYPES = new Set(["table", "schema", "endpoint"]);
  const CONFIG_TYPES = new Set(["config"]);
  const pick = (n) => ({
    id: n.id, name: n.name, type: n.type, summary: n.summary || "",
  });
  const nonCodeFiles = {
    documentation: nodes.filter((n) => DOC_DOC_TYPES.has(n.type)).map(pick),
    infrastructure: nodes.filter((n) => INFRA_TYPES.has(n.type)).map(pick),
    data: nodes.filter((n) => DATA_TYPES.has(n.type)).map(pick),
    config: nodes.filter((n) => CONFIG_TYPES.has(n.type)).map(pick),
  };

  // ---- F. tightly coupled clusters ---------------------------------------
  // Step 1: bidirectional dependency pairs (A->B and B->A over DEP_TYPES).
  const dirSet = new Set();
  for (const e of edges) {
    if (DEP_TYPES.has(e.type)) dirSet.add(e.source + "\u0000" + e.target);
  }
  const biPairs = [];
  for (const key of dirSet) {
    const [a, b] = key.split("\u0000");
    if (a < b && dirSet.has(b + "\u0000" + a)) biPairs.push([a, b]);
  }

  // Step 2: expansion/fallback. Seed from each node's strongest neighbourhood,
  // keeping members with >=2 internal connections (seed counts as one link).
  const clusterKey = (set) => [...set].sort().join("\u0001");
  const raw = [];
  const seedsSeen = new Set();
  const seeds = nodes
    .map((n) => n.id)
    .sort((a, b) =>
      (undirected.get(b).size - undirected.get(a).size) || a.localeCompare(b));
  for (const s of seeds.slice(0, 40)) {
    const nbrs = [...undirected.get(s)];
    if (nbrs.length < 2) continue;
    // rank neighbours by their connectivity back into {seed} u neighbours
    const ranked = nbrs.sort((a, b) => {
      const ca = countLinks(a, s, undirected);
      const cb = countLinks(b, s, undirected);
      return cb - ca || a.localeCompare(b);
    });
    const cluster = new Set([s]);
    for (const c of ranked) {
      if (cluster.size >= 5) break;
      cluster.add(c);
    }
    // prune members without >=2 internal links (seed itself exempt)
    const kept = new Set([s]);
    for (const m of cluster) {
      if (m === s) continue;
      let links = 0;
      for (const o of cluster) {
        if (o !== m && undirected.get(m).has(o)) links++;
      }
      if (links >= 2) kept.add(m);
    }
    if (kept.size < 3) continue;
    const key = clusterKey(kept);
    if (seedsSeen.has(key)) continue;
    seedsSeen.add(key);
    let edgeCount = 0;
    for (const m of kept) {
      for (const o of kept) {
        if (m !== o && undirected.get(m).has(o)) edgeCount++;
      }
    }
    edgeCount /= 2;
    raw.push({ nodes: [...kept].sort(), edgeCount });
  }

  // merge heavily-overlapping clusters, keep strongest
  raw.sort((a, b) => b.edgeCount - a.edgeCount || b.nodes.length - a.nodes.length);
  const finalClusters = [];
  for (const cl of raw) {
    const cs = new Set(cl.nodes);
    let dup = false;
    for (const keep of finalClusters) {
      const ks = new Set(keep.nodes);
      let inter = 0;
      for (const m of cs) if (ks.has(m)) inter++;
      const union = new Set([...cs, ...ks]).size;
      if (inter / union > 0.6) { dup = true; break; }
    }
    if (!dup) finalClusters.push(cl);
    if (finalClusters.length >= 10) break;
  }
  // always surface explicit bidirectional pairs even if sparse
  for (const [a, b] of biPairs.slice(0, 5)) {
    if (finalClusters.length >= 10) break;
    finalClusters.push({ nodes: [a, b], edgeCount: 2, bidirectional: true });
  }
  const clusters = finalClusters.slice(0, 10);

  // ---- G. layers ----------------------------------------------------------
  const layerOut = { count: layers.length, list: layers };

  // ---- H. node summary index ----------------------------------------------
  const nodeSummaryIndex = {};
  for (const n of nodes) {
    nodeSummaryIndex[n.id] = { name: n.name, type: n.type, summary: n.summary || "" };
  }

  const out = {
    scriptCompleted: true,
    entryPointCandidates,
    fanInRanking,
    fanOutRanking,
    bfsTraversal,
    nonCodeFiles,
    clusters,
    layers: layerOut,
    nodeSummaryIndex,
    totalNodes: nodes.length,
    totalEdges: edges.length,
  };
  try {
    fs.writeFileSync(outputPath, JSON.stringify(out, null, 2) + "\n");
  } catch (e) {
    console.error("fatal: cannot write output: " + e.message);
    process.exit(1);
  }
  process.exit(0);
}

function nameOf(id) {
  const i = id.lastIndexOf("/");
  return i === -1 ? id : id.slice(i + 1);
}

function isCodeLike(n) {
  return n.type === "file";
}

function countLinks(x, seed, undirected) {
  // how strongly x ties into the growing cluster around seed
  let c = 0;
  if (undirected.get(x).has(seed)) c++;
  for (const y of undirected.get(x)) {
    if (y !== seed && undirected.get(seed).has(y)) c++;
  }
  return c;
}

try {
  main();
} catch (e) {
  console.error("fatal: " + (e && e.stack ? e.stack : String(e)));
  process.exit(1);
}
