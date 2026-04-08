import fs from 'node:fs'
import path from 'node:path'

const ROOT = process.cwd()
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
  /Ã./u,
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
