#!/usr/bin/env node
// npx heard ... -> runs the Python heard CLI of the same version through uv (uvx), passing everything through.
// HEARD_FROM overrides what uv installs, e.g. a git URL or a local checkout: HEARD_FROM=git+https://github.com/WinexWolf/Heard
'use strict'
const { spawn, spawnSync } = require('node:child_process')
const { constants } = require('node:os')
const { version } = require('../package.json')

const spec = process.env.HEARD_FROM || `heard==${version}`
const args = process.argv.slice(2)

const works = cmd => {
  const r = spawnSync(cmd, ['--version'], { stdio: 'ignore' })
  return !r.error && r.status === 0
}

const runner = works('uvx') ? ['uvx', ['--from', spec, 'heard', ...args]]
  : works('uv') ? ['uv', ['tool', 'run', '--from', spec, 'heard', ...args]]
  : null

if (!runner) {
  process.stderr.write([
    'heard runs on uv, the Python package runner, which was not found on PATH.',
    'Install it, then run the same command again:',
    '',
    '  macOS / Linux:  curl -LsSf https://astral.sh/uv/install.sh | sh',
    '  Homebrew:       brew install uv',
    '  Windows:        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"',
    '  GitHub Actions: - uses: astral-sh/setup-uv@v6',
    '',
    'Or skip npm entirely: uvx heard ' + args.join(' '),
    '',
  ].join('\n'))
  process.exit(127)
}

const child = spawn(runner[0], runner[1], { stdio: 'inherit' })
// Ctrl-C reaches the child through the terminal's process group; stay alive so its exit code is reported.
process.on('SIGINT', () => {})
process.on('SIGTERM', () => child.kill('SIGTERM'))
child.on('error', e => {
  process.stderr.write(`heard: could not start ${runner[0]}: ${e.message}\n`)
  process.exit(1)
})
child.on('exit', (code, signal) => {
  process.exit(signal ? 128 + (constants.signals[signal] ?? 1) : code ?? 1)
})
