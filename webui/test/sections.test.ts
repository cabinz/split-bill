/**
 * The report's structure: what renders, what it is numbered, and how the prose cites it.
 *
 * These used to be four assertions inside the view-model tests, because a section was a
 * literal with its number written on it. Now the numbers are derived, and what has to be
 * tested is the derivation -- particularly the two cases the old shape could not express:
 *
 *   * a bill with no category column, where the section after the missing one has to take its
 *     number rather than leaving a gap;
 *   * an export that leaves an appendix out, where the letters after it have to close up and
 *     every reference to them has to follow.
 *
 * The second is the one worth having a test for at all. A stale "see Appendix C" in a document
 * whose Appendix C is now the sheet is not a layout blemish -- it sends the reader to the
 * wrong table and there is nothing on the page to reveal the mistake.
 */
import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  BODY_SECTIONS,
  CHECKING_SECTIONS,
  MEMBER_TABLE_NOTES,
  appendix,
  aroundRef,
  bodySection,
  crossRef,
  printId,
  resolve,
  sectionHint,
  subsection,
} from '../src/presentation/sections'

/** Everything included, which is the full report. */
const EVERYTHING = { appendix: true, statements: true }
const CATEGORISED = { categories: true }

/** A key, rendered as its own name, so a test can see which key was used. */
const key = (name: string, params: Record<string, string | number> = {}) => {
  const inner = Object.entries(params)
    .map(([field, value]) => `${field}=${value}`)
    .join(',')
  return inner ? `[${name} ${inner}]` : `[${name}]`
}

describe('numbering the body', () => {
  it('starts the report at 1, the import stepper being a different thing', () => {
    // It used to start at 2, because the stepper's "1 · Load data" was counted as the report's
    // first section. They are two numbering schemes over two different things.
    const structure = resolve('screen', CATEGORISED, EVERYTHING)
    assert.equal(bodySection(structure, 'overview')?.number, 1)
  })

  it('numbers the visible sections consecutively', () => {
    const structure = resolve('screen', CATEGORISED, EVERYTHING)
    assert.deepEqual(
      structure.body.map((entry) => [entry.id, entry.number]),
      [
        ['overview', 1],
        ['members', 2],
        ['settle', 3],
        ['categories', 4],
        ['details', 5],
      ],
    )
  })

  it('closes the gap when a bill has no categories', () => {
    const structure = resolve('screen', { categories: false }, EVERYTHING)
    assert.deepEqual(
      structure.body.map((entry) => [entry.id, entry.number]),
      [['overview', 1], ['members', 2], ['settle', 3], ['details', 4]],
    )
    assert.equal(bodySection(structure, 'categories'), undefined)
  })

  it('leaves the sections before the missing one where they were', () => {
    // The whole point of deriving them: "how to settle" is 3 either way, so a sentence
    // referring to it is right in both reports.
    for (const categories of [true, false]) {
      assert.equal(bodySection(resolve('screen', { categories }, EVERYTHING), 'settle')
        ?.number, 3)
    }
  })

  it('numbers subsections from their parent’s current number', () => {
    const structure = resolve('screen', CATEGORISED, EVERYTHING)
    assert.equal(subsection(structure, 'settle', 'pool')?.label, '3.1')
    assert.equal(subsection(structure, 'settle', 'transfers')?.label, '3.2')
    assert.equal(subsection(structure, 'categories', 'categoryTotals')?.label, '4.1')
  })

  it('renumbers subsections when the parent moves', () => {
    const structure = resolve('screen', { categories: false }, EVERYTHING)
    // details is 4 rather than 5 here, so its subsections are 4.x.
    assert.equal(subsection(structure, 'details', 'lending')?.label, '4.1')
    assert.equal(subsection(structure, 'details', 'sheet')?.label, '4.4')
  })

  it('gives every defined section a title and a nav label', () => {
    for (const definition of BODY_SECTIONS) {
      assert.equal(typeof definition.titleKey, 'string', definition.id)
      assert.equal(typeof definition.navKey, 'string', definition.id)
    }
  })
})

describe('the checking tables, screen and paper', () => {
  it('makes them numbered subsections on screen and no appendices', () => {
    const structure = resolve('screen', CATEGORISED, EVERYTHING)
    assert.deepEqual(structure.appendices, [])
    assert.deepEqual(
      bodySection(structure, 'details')?.subsections.map((entry) => entry.id),
      ['lending', 'statements', 'allocation', 'sheet'],
    )
  })

  it('makes them lettered appendices on paper, and drops the numbered section', () => {
    const structure = resolve('print', CATEGORISED, EVERYTHING)
    assert.equal(bodySection(structure, 'details'), undefined)
    assert.deepEqual(
      structure.appendices.map((entry) => [entry.id, entry.letter]),
      [
        ['lending', 'A'],
        ['statements', 'B'],
        ['allocation', 'C'],
        ['sheet', 'D'],
      ],
    )
  })

  it('leaves the printed body numbered as though the appendices were not there', () => {
    // A..D and 1..4 are separate sequences: the body is the same document whether or not the
    // appendices are printed, so its numbers must not move when they are excluded.
    const structure = resolve('print', CATEGORISED, EVERYTHING)
    assert.deepEqual(
      structure.body.map((entry) => entry.number),
      [1, 2, 3, 4],
    )
  })

  it('closes up the letters when the statements are left out', () => {
    const structure = resolve('print', CATEGORISED, { appendix: true, statements: false })
    assert.deepEqual(
      structure.appendices.map((entry) => [entry.id, entry.letter]),
      [['lending', 'A'], ['allocation', 'B'], ['sheet', 'C']],
    )
  })

  it('produces no appendices at all when the master switch is off', () => {
    const structure = resolve('print', CATEGORISED, { appendix: false, statements: true })
    assert.deepEqual(structure.appendices, [])
  })

  it('drops the screen’s checking section too when nothing would be in it', () => {
    const structure = resolve('screen', CATEGORISED, { appendix: false, statements: false })
    assert.equal(bodySection(structure, 'details'), undefined)
    // And the body closes up behind it rather than ending at a heading with nothing under it.
    assert.deepEqual(
      structure.body.map((entry) => entry.number),
      [1, 2, 3, 4],
    )
  })

  it('names the statements differently in each medium, being different content', () => {
    // One member at a time on screen, because it can be changed; every member on paper,
    // because it cannot.
    const statements = CHECKING_SECTIONS.find((entry) => entry.id === 'statements')!
    assert.notEqual(statements.screenTitleKey, statements.printTitleKey)
  })
})

describe('citing a checking table from the prose', () => {
  it('cites a numbered subsection on screen', () => {
    const structure = resolve('screen', CATEGORISED, EVERYTHING)
    const ref = crossRef(structure, 'allocation', key)
    assert.equal(ref?.label, '[ref.section number=5.3,title=[appendix.allocation]]')
    assert.equal(ref?.anchor, 'allocation')
  })

  it('cites a lettered appendix on paper', () => {
    const structure = resolve('print', CATEGORISED, EVERYTHING)
    const ref = crossRef(structure, 'allocation', key)
    assert.equal(ref?.label, '[ref.appendix letter=C,title=[appendix.allocation]]')
    assert.equal(ref?.anchor, 'print-allocation')
  })

  it('follows the letters when an earlier appendix is excluded', () => {
    // The failure this test exists for: with the statements left out the allocation is B, and
    // a reference reading "Appendix C" would send the reader to the source sheet.
    const structure = resolve('print', CATEGORISED, { appendix: true, statements: false })
    assert.equal(
      crossRef(structure, 'allocation', key)?.label,
      '[ref.appendix letter=B,title=[appendix.allocation]]',
    )
  })

  it('returns nothing for a table this export does not contain', () => {
    // So the caller omits the sentence. A reference kept alive by forcing an appendix into
    // the export would make the export options a lie.
    const structure = resolve('print', CATEGORISED, { appendix: true, statements: false })
    assert.equal(crossRef(structure, 'statements', key), null)
    const bare = resolve('print', CATEGORISED, { appendix: false, statements: false })
    for (const id of ['lending', 'statements', 'allocation', 'sheet'] as const) {
      assert.equal(crossRef(bare, id, key), null, id)
    }
  })

  it('names the thing as well as its number, for a reader holding paper', () => {
    // "See Appendix A" beside no hyperlink has to say what is in Appendix A.
    const structure = resolve('print', CATEGORISED, EVERYTHING)
    const ref = crossRef(structure, 'lending', key)
    assert.equal(ref!.label.includes('title='), true, ref!.label)
  })

  it('splits a sentence around its reference, for a link in the middle of it', () => {
    assert.deepEqual(aroundRef('every share is in {ref}.'), {
      before: 'every share is in ',
      after: '.',
    })
  })

  it('keeps the whole sentence when a translation drops the placeholder', () => {
    // Losing the link is recoverable; losing the sentence is not.
    assert.deepEqual(aroundRef('no placeholder here'), {
      before: 'no placeholder here',
      after: '',
    })
  })
})

describe('print anchors', () => {
  it('prefixes them, so both DOMs can be in one document', () => {
    // When printing from the report window the screen tree and the print tree are both in the
    // document, and duplicate ids would be invalid HTML and ambiguous to every selector.
    assert.equal(printId('allocation'), 'print-allocation')
    for (const definition of BODY_SECTIONS) {
      assert.notEqual(printId(definition.id), definition.id)
    }
  })
})

describe('section standfirsts', () => {
  it('gives both media the shared substance', () => {
    for (const medium of ['screen', 'print'] as const) {
      const structure = resolve(medium, CATEGORISED, EVERYTHING)
      assert.equal(
        sectionHint(bodySection(structure, 'members'), medium, key).includes(
          '[members.hint]',
        ),
        true,
        medium,
      )
    }
  })

  it('never puts a screen affordance on paper', () => {
    // The bug this exists for: a shared standfirst said "Expand a row to see the records it is
    // made of", and the first PDF printed that instruction beside a table with nothing to
    // expand.
    const structure = resolve('print', CATEGORISED, EVERYTHING)
    for (const entry of structure.body) {
      assert.equal(
        sectionHint(entry, 'print', key).includes('hintScreen'),
        false,
        `${entry.id} prints a screen-only sentence`,
      )
    }
  })

  it('gives the screen its own closing sentence where there is one', () => {
    const structure = resolve('screen', CATEGORISED, EVERYTHING)
    const hint = sectionHint(bodySection(structure, 'details'), 'screen', key)
    assert.equal(hint.includes('[details.hint]'), true, hint)
    assert.equal(hint.includes('[details.hintScreen]'), true, hint)
  })

  it('returns nothing for a section whose standfirst is built from the report', () => {
    // The overview states figures in its own, so it has no static key.
    const structure = resolve('screen', CATEGORISED, EVERYTHING)
    assert.equal(sectionHint(bodySection(structure, 'overview'), 'screen', key), '')
  })

  it('returns nothing for a section that does not render', () => {
    const structure = resolve('screen', { categories: false }, EVERYTHING)
    assert.equal(sectionHint(bodySection(structure, 'categories'), 'screen', key), '')
  })
})

describe('the member table’s notes', () => {
  it('states both routes to the outstanding figure', () => {
    // The point of the list. `paid - consumed` and `covered for - covered by` are the same
    // number, and a reader who checks either has checked the report rather than trusted it.
    assert.equal(MEMBER_TABLE_NOTES.includes('members.formulaPaid'), true)
    assert.equal(MEMBER_TABLE_NOTES.includes('members.formulaCovered'), true)
  })

  it('says what each of the four columns means, and what the sign means', () => {
    for (const note of [
      'members.explainConsumed',
      'members.explainPaid',
      'members.explainCoveredFor',
      'members.explainCoveredBy',
      'members.explainSign',
    ]) {
      assert.equal(MEMBER_TABLE_NOTES.includes(note), true, note)
    }
  })
})

describe('appendix lookup', () => {
  it('finds one by id', () => {
    const structure = resolve('print', CATEGORISED, EVERYTHING)
    assert.equal(appendix(structure, 'sheet')?.letter, 'D')
  })

  it('finds nothing on screen, where there are none', () => {
    assert.equal(appendix(resolve('screen', CATEGORISED, EVERYTHING), 'sheet'), undefined)
  })
})
