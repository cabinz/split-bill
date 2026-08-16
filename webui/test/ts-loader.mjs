/**
 * Run the TypeScript unit tests without adding a test runner.
 *
 * `node --test` is the standard library and esbuild is already here as Vite's dependency,
 * so the whole cost of unit-testing the presentation layer is this file. A test framework
 * would be a second dependency to pin -- and pinning matters unusually much in this
 * repository, because the built bundle is committed and has to be reproducible from the
 * source beside it.
 *
 * It only has to handle what the tests import: relative TypeScript, and bare specifiers
 * that Node can already resolve from node_modules. Type-checking is `vue-tsc` during the
 * build, not here; this strips types and does not check them.
 *
 *   node --import ./test/ts-loader.mjs --test test/
 */
import { readFile } from 'node:fs/promises'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { register } from 'node:module'
import { transform } from 'esbuild'

// The hooks below run on a worker thread, so they are registered rather than exported.
if (!process.env.SPLITBILL_TS_LOADER) {
  process.env.SPLITBILL_TS_LOADER = '1'
  register(import.meta.url, pathToFileURL('./'))
}

/** Extensionless relative imports, which TypeScript allows and Node does not. */
export async function resolve(specifier, context, nextResolve) {
  try {
    return await nextResolve(specifier, context)
  } catch (failure) {
    if (specifier.startsWith('.') && !specifier.endsWith('.ts')) {
      return nextResolve(`${specifier}.ts`, context)
    }
    throw failure
  }
}

export async function load(url, context, nextLoad) {
  if (!url.endsWith('.ts')) return nextLoad(url, context)
  const source = await readFile(fileURLToPath(url), 'utf-8')
  const { code } = await transform(source, {
    loader: 'ts',
    format: 'esm',
    target: 'node20',
    sourcefile: fileURLToPath(url),
    sourcemap: 'inline',
  })
  return { format: 'module', shortCircuit: true, source: code }
}
