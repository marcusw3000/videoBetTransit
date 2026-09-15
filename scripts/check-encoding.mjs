import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const SCAN_PATHS = [
  'frontend/src',
  'backend/TrafficCounter.Api',
  'vision-worker',
  'app.py',
  'backend_client.py',
]

const IGNORE_DIRS = new Set([
  '.git',
  'node_modules',
  'dist',
  'bin',
  'obj',
  'publish_dev',
  'traffic-counter-front',
  'logs',
])

const TEXT_EXTENSIONS = new Set([
  '.bat',
  '.cmd',
  '.css',
  '.cs',
  '.csproj',
  '.html',
  '.js',
  '.json',
  '.jsx',
  '.md',
  '.mjs',
  '.ps1',
  '.py',
  '.xml',
  '.yml',
  '.yaml',
])

const SUSPICIOUS_PATTERNS = [
  /\u00c3[\u0080-\u00bf\u0152\u0153\u0160\u0161\u0178\u017d\u017e\u0192\u02c6\u02dc\u2013-\u203a\u20ac\u2122]/u,
  /â€”/u,
  /â€"/u,
  /â€˜/u,
  /â€™/u,
  /â†/u,
  /â–/u,
  /ðŸ/u,
  /�/u,
]

const problems = []

function shouldScanFile(filePath) {
  return TEXT_EXTENSIONS.has(path.extname(filePath).toLowerCase())
}

function walk(relativePath) {
  const fullPath = path.join(ROOT, relativePath)

  if (!fs.existsSync(fullPath)) {
    return
  }

  const stats = fs.statSync(fullPath)
  if (stats.isDirectory()) {
    const dirName = path.basename(fullPath)
    if (IGNORE_DIRS.has(dirName)) {
      return
    }

    for (const entry of fs.readdirSync(fullPath)) {
      walk(path.join(relativePath, entry))
    }
    return
  }

  if (!shouldScanFile(fullPath)) {
    return
  }

  const content = fs.readFileSync(fullPath, 'utf8')
  const lines = content.split(/\r?\n/u)

  lines.forEach((line, index) => {
    if (SUSPICIOUS_PATTERNS.some((pattern) => pattern.test(line))) {
      problems.push({
        file: relativePath.replace(/\\/gu, '/'),
        line: index + 1,
        text: line.trim(),
      })
    }
  })
}

for (const target of SCAN_PATHS) {
  walk(target)
}

if (problems.length > 0) {
  console.error('Encoding check failed. Suspected mojibake found:')
  for (const problem of problems) {
    console.error(`- ${problem.file}:${problem.line} ${problem.text}`)
  }
  process.exit(1)
}

console.log('Encoding check passed for active code.')
