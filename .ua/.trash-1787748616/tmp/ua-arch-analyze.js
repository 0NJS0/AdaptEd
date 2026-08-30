#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');

function fail(msg) {
  process.stderr.write(`ERROR: ${msg}\n`);
  process.exit(1);
}

const inputPath = process.argv[2];
const outputPath = process.argv[3];
if (!inputPath || !outputPath) {
  fail('usage: ua-arch-analyze.js <input.json> <output.json>');
}

let input;
try {
  input = JSON.parse(fs.readFileSync(inputPath, 'utf8'));
} catch (e) {
  fail(`cannot read/parse input: ${e.message}`);
}

const fileNodes = Array.isArray(input.fileNodes) ? input.fileNodes : [];
const importEdges = Array.isArray(input.importEdges) ? input.importEdges : [];
const allEdges = Array.isArray(input.allEdges) ? input.allEdges : [];

if (fileNodes.length === 0) fail('no file nodes in input');

// ---------- helpers ----------
function segments(filePath) {
  return filePath.split('/').filter(Boolean);
}

function commonDirPrefix(paths) {
  // longest common directory prefix across all paths
  let segs = paths.map(segments).map((s) => s.slice(0, -1)); // drop filename
  if (segs.length === 0) return [];
  let prefix = segs[0];
  for (const s of segs.slice(1)) {
    let i = 0;
    while (i < prefix.length && i < s.length && prefix[i] === s[i]) i++;
    prefix = prefix.slice(0, i);
    if (prefix.length === 0) break;
  }
  return prefix;
}

const nodeById = new Map();
for (const n of fileNodes) nodeById.set(n.id, n);

// ---------- A. directory grouping ----------
const paths = fileNodes.map((n) => n.filePath);
const prefix = commonDirPrefix(paths);
const prefixLen = prefix.length;

function groupOf(node) {
  const segs = segments(node.filePath);
  const rel = segs.slice(prefixLen);
  const isFile = !node.filePath.endsWith('/');
  if (rel.length === 0) return '(root)';
  if (isFile) {
    if (rel.length === 1) return '(root)';
    return rel[0];
  }
  return rel[0] || '(root)';
}

const directoryGroups = {};
for (const n of fileNodes) {
  const g = groupOf(n);
  (directoryGroups[g] = directoryGroups[g] || []).push(n.id);
}

// ---------- B. node type grouping ----------
const nodeTypeGroups = {};
for (const n of fileNodes) {
  (nodeTypeGroups[n.type] = nodeTypeGroups[n.type] || []).push(n.id);
}

// ---------- C. adjacency / fan-in / fan-out ----------
const fanIn = {};
const fanOut = {};
for (const e of importEdges) {
  if (!nodeById.has(e.source) || !nodeById.has(e.target)) continue;
  fanOut[e.source] = (fanOut[e.source] || 0) + 1;
  fanIn[e.target] = (fanIn[e.target] || 0) + 1;
}
const sortedFanIn = Object.fromEntries(
  Object.entries(fanIn).sort((a, b) => b[1] - a[1])
);
const sortedFanOut = Object.fromEntries(
  Object.entries(fanOut).sort((a, b) => b[1] - a[1])
);

// ---------- D. cross-category edges (allEdges) ----------
const crossMap = new Map();
for (const e of allEdges) {
  const s = nodeById.get(e.source);
  const t = nodeById.get(e.target);
  if (!s || !t) continue;
  if (s.type === t.type && s.type === 'file') continue; // only cross-category
  const key = `${s.type}|${t.type}|${e.type}`;
  crossMap.set(key, (crossMap.get(key) || 0) + 1);
}
const crossCategoryEdges = [...crossMap.entries()].map(([k, count]) => {
  const [fromType, toType, edgeType] = k.split('|');
  return { fromType, toType, edgeType, count };
});

// ---------- E/F. inter- and intra-group imports ----------
const interMap = new Map();
const intraInternal = {};
const intraTotal = {};
for (const e of importEdges) {
  const s = nodeById.get(e.source);
  const t = nodeById.get(e.target);
  if (!s || !t) continue;
  const gs = groupOf(s);
  const gt = groupOf(t);
  intraTotal[gs] = (intraTotal[gs] || 0) + 1;
  if (gs === gt) {
    intraInternal[gs] = (intraInternal[gs] || 0) + 1;
  } else {
    const key = `${gs}|${gt}`;
    interMap.set(key, (interMap.get(key) || 0) + 1);
  }
}
const interGroupImports = [...interMap.entries()]
  .map(([k, count]) => {
    const [from, to] = k.split('|');
    return { from, to, count };
  })
  .sort((a, b) => b.count - a.count);

const intraGroupDensity = {};
for (const g of Object.keys(directoryGroups)) {
  const internal = intraInternal[g] || 0;
  const total = intraTotal[g] || 0;
  intraGroupDensity[g] = {
    internalEdges: internal,
    totalEdges: total,
    density: total > 0 ? +(internal / total).toFixed(2) : 0,
  };
}

// ---------- G. pattern matching ----------
const dirPatterns = [
 [/^(routes|api|controllers|endpoints|handlers|serializers|routers|blueprints)$/, 'api'],
 [/^(services|core|lib|domain|logic|signals|composables|mailers|jobs|channels)$/, 'service'],
 [/^(models|db|data|persistence|repository|entities|migrations|sql|database|schema|entity)$/, 'data'],
 [/^(components|views|pages|ui|layouts|screens)$/, 'ui'],
 [/^(middleware|plugins|interceptors|guards)$/, 'middleware'],
 [/^(utils|helpers|common|shared|tools|pkg|templatetags)$/, 'utility'],
 [/^(config|constants|env|settings|management|commands)$/, 'config'],
 [/^(__tests__|test|tests|spec|specs)$/, 'test'],
 [/^(types|interfaces|schemas|contracts|dtos|dto|request|response)$/, 'types'],
 [/^hooks$/, 'hooks'],
 [/^(store|state|reducers|actions|slices)$/, 'state'],
 [/^(assets|static|public)$/, 'assets'],
 [/^(cmd|bin)$/, 'entry'],
 [/^internal$/, 'service'],
 [/^(docs|documentation|wiki)$/, 'documentation'],
 [/^(deploy|deployment|infra|infrastructure|docker)$/, 'infrastructure'],
 [/^(\.github|\.gitlab|\.circleci)$/, 'ci-cd'],
];

function classifyGroup(group) {
  const base = path.basename(group);
  for (const [re, label] of dirPatterns) {
    if (re.test(base)) return label;
  }
  return null;
}

const patternMatches = {};
for (const g of Object.keys(directoryGroups)) {
  const m = classifyGroup(g);
  if (m) patternMatches[g] = m;
}

// file-level pattern classification (per node, supplementary)
const fileLevelPatterns = {};
for (const n of fileNodes) {
  const p = n.filePath;
  const base = path.basename(p);
  let label = null;
  if (/(\.test\.|\.spec\.|^test_.*\.py$|_test\.go$|Test\.java$|_spec\.rb$)/.test(base)) label = 'test';
  else if (/\.d\.ts$/.test(base)) label = 'types';
  else if (base === '__init__.py' || base === 'index.ts' || base === 'index.js') label = 'entry';
  else if (base === 'main.py' && p.split('/').length <= prefixLen + 2) label = 'entry';
  else if (base === 'manage.py') label = 'entry';
  else if (base === 'wsgi.py' || base === 'asgi.py') label = 'config';
  else if (/^(Cargo\.toml|go\.mod|Gemfile|pom\.xml|build\.gradle|composer\.json)$/.test(base)) label = 'config';
  else if (base === 'Dockerfile' || /^docker-compose\./.test(base)) label = 'infrastructure';
  else if (/\.tf$/.test(base)) label = 'infrastructure';
  else if (/\.github\/workflows\//.test(p) || base === '.gitlab-ci.yml' || base === 'Jenkinsfile') label = 'ci-cd';
  else if (/\.sql$/.test(base)) label = 'data';
  else if (/\.(graphql|gql|proto)$/.test(base)) label = 'types';
  else if (/\.(md|rst)$/.test(base)) label = 'documentation';
  else if (base === 'Makefile') label = 'infrastructure';
  if (label) fileLevelPatterns[n.id] = label;
}

// ---------- H. deployment topology ----------
const infraFiles = [];
let hasDockerfile = false, hasCompose = false, hasK8s = false, hasTerraform = false, hasCI = false;
for (const n of fileNodes) {
  const p = n.filePath;
  const base = path.basename(p);
  if (base === 'Dockerfile' || /Dockerfile/.test(base)) { hasDockerfile = true; infraFiles.push(p); }
  else if (/^docker-compose/.test(base)) { hasCompose = true; infraFiles.push(p); }
  else if (/k8s|kubernetes|helm/.test(p)) { hasK8s = true; infraFiles.push(p); }
  else if (/\.tf(vars)?$/.test(base)) { hasTerraform = true; infraFiles.push(p); }
  else if (/\.github\/workflows\/|\.gitlab-ci\.yml|Jenkinsfile/.test(p)) { hasCI = true; infraFiles.push(p); }
}

// ---------- I. data pipeline detection ----------
const dataPipeline = {
  schemaFiles: [],
  migrationFiles: [],
  dataModelFiles: [],
  apiHandlerFiles: [],
};
for (const n of fileNodes) {
  const p = n.filePath;
  const tags = n.tags || [];
  if (/\.sql$/.test(p) || /\.(graphql|proto|prisma)$/.test(p)) dataPipeline.schemaFiles.push(p);
  if (/migrations?\//.test(p)) dataPipeline.migrationFiles.push(p);
  if (/\/models?\/|\/models?\.py$/.test(p) || tags.includes('data-model')) dataPipeline.dataModelFiles.push(p);
  if (/\/routers?\//.test(p) || tags.includes('api-handler')) dataPipeline.apiHandlerFiles.push(p);
}

// ---------- J. documentation coverage ----------
const docRe = /\.(md|rst)$/;
const groupDocs = new Set();
for (const n of fileNodes) {
  if (docRe.test(path.basename(n.filePath))) groupDocs.add(groupOf(n));
}
const allGroups = Object.keys(directoryGroups);
const undocumentedGroups = allGroups.filter((g) => !groupDocs.has(g));
const docCoverage = {
  groupsWithDocs: groupDocs.size,
  totalGroups: allGroups.length,
  coverageRatio: +((groupDocs.size / allGroups.length)).toFixed(2),
  undocumentedGroups,
};

// ---------- K. dependency direction ----------
const pairNet = new Map(); // "a|b" (a<b) -> {a:count,b:count}
for (const { from, to, count } of interGroupImports) {
  const [a, b] = [from, to].sort();
  const key = `${a}|${b}`;
  const rec = pairNet.get(key) || { a: 0, b: 0 };
  if (from === a) rec.a += count; else rec.b += count;
  pairNet.set(key, rec);
}
const dependencyDirection = [];
for (const [key, rec] of pairNet) {
  const [a, b] = key.split('|');
  if (rec.a > rec.b) dependencyDirection.push({ dependent: a, dependsOn: b });
  else if (rec.b > rec.a) dependencyDirection.push({ dependent: b, dependsOn: a });
  else { dependencyDirection.push({ dependent: a, dependsOn: b }); dependencyDirection.push({ dependent: b, dependsOn: a }); }
}

// ---------- files per group / node type counts ----------
const filesPerGroup = {};
for (const [g, ids] of Object.entries(directoryGroups)) filesPerGroup[g] = ids.length;
const nodeTypeCounts = {};
for (const [t, ids] of Object.entries(nodeTypeGroups)) nodeTypeCounts[t] = ids.length;

// ---------- output ----------
const result = {
  scriptCompleted: true,
  commonPrefix: prefix.join('/'),
  directoryGroups,
  nodeTypeGroups,
  crossCategoryEdges,
  interGroupImports,
  intraGroupDensity,
  patternMatches,
  fileLevelPatterns,
  deploymentTopology: {
    hasDockerfile, hasCompose, hasK8s, hasTerraform, hasCI,
    infraFiles,
  },
  dataPipeline,
  docCoverage,
  dependencyDirection,
  fileStats: {
    totalFileNodes: fileNodes.length,
    filesPerGroup,
    nodeTypeCounts,
  },
  fileFanIn: sortedFanIn,
  fileFanOut: sortedFanOut,
};

try {
  fs.writeFileSync(outputPath, JSON.stringify(result, null, 2));
} catch (e) {
  fail(`cannot write output: ${e.message}`);
}
process.exit(0);
