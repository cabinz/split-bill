/**
 * The report's structure, defined once and numbered from what actually renders.
 *
 * The numbers in the headings are not decoration: the prose refers to them ("the pool is
 * 3.1"), so a section that is 4 on screen and 3 on paper makes the report wrong rather
 * than merely inconsistent. They used to be stored -- `overview` was literally `number:
 * 2`, because the import stepper was counted as section 1 -- and that made every
 * conditional section impossible: drop one and the rest of the report is misnumbered.
 *
 * So nothing here stores a number. A definition declares a stable `id`, its titles, and
 * when it renders; the numbers come from the order of the *visible* ones. Two consequences
 * worth stating because both are requirements:
 *
 *   * The import stepper and the report's chapters are separate things. The report starts
 *     at 1 in both views.
 *   * A bill with no category column has no category section, and the section after it is
 *     numbered as though it never existed. Nothing has to be renumbered by hand.
 *
 * The two views share the body and diverge after it. The screen's checking tables are
 * numbered sections like any other; on paper the same content is lettered appendices, each
 * starting a new page, because a 20-page ledger in the middle of the body would bury the
 * settlement. `resolve()` produces both from one list, and `crossRef()` is how the prose
 * cites a target without knowing which form it took.
 *
 * `id` is the screen anchor. The print view prefixes it with `print-`, because when
 * printing from the report window both DOMs are in one document and duplicate ids would be
 * invalid HTML and ambiguous to every selector in the test suite.
 */

/** Every section of the body, in the order they are defined. */
export type BodySectionId =
  | 'overview'
  | 'members'
  | 'settle'
  | 'categories'
  | 'details'

/**
 * The checking tables, which are subsections on screen and appendices on paper.
 *
 * One id per piece of content, shared between the two forms, which is what lets a
 * cross-reference name a target without knowing whether it will come out as "5.3" or as
 * "Appendix C".
 *
 * `statements` is the one place the two forms differ in substance rather than in
 * presentation, and deliberately: on screen it is one paginated table with a member picker
 * over it, on paper it is every member's table in turn. A screen picker cannot be printed
 * -- there would be no way to change it -- so the printed form is all members or none, and
 * which it is comes from an export option rather than from whoever the screen was left
 * showing.
 */
export type CheckingId = 'lending' | 'statements' | 'allocation' | 'sheet'

export type SectionId = BodySectionId | CheckingId

/** Which subsections a body section has. Only `settle` and `categories` have fixed ones;
 *  `details` takes the checking list, which the export options can shorten. */
export interface SubsectionDefinition {
  id: string
  titleKey: string
}

export interface BodySectionDefinition {
  id: BodySectionId
  /** i18n key for the heading. */
  titleKey: string
  /** i18n key for the nav label, which is sometimes shorter than the heading. */
  navKey: string
  /** i18n key for the standfirst. Absent where it depends on the report -- the overview
   *  and the settlement both state figures in theirs. */
  hintKey?: string
  /**
   * A sentence only the screen's standfirst gets, where the shared one would otherwise
   * have to describe an affordance.
   *
   * "Expand a row to see the records it is made of" is true on screen and nonsense on
   * paper, and the first PDF printed it. The alternative -- two complete standfirsts, one
   * per view -- would be the same paragraph translated twice, drifting independently. So
   * the substance stays in `hintKey` and only the sentence that differs lives here.
   */
  screenHintKey?: string
  /** The same, for the printed report. */
  printHintKey?: string
  /** Fixed subsections. `details` has none here: its subsections are the checking list. */
  subsections?: readonly SubsectionDefinition[]
  /** True for the section whose subsections are the checking tables. Exactly one is. */
  checking?: true
  /** Whether this section renders at all for a given report. Absent means always. */
  when?: (context: ReportShape) => boolean
}

/** What the structure needs to know about a report to decide what renders. */
export interface ReportShape {
  /** Whether any member has a category breakdown worth charting. */
  categories: boolean
}

/** What the structure needs to know about an export to decide which appendices exist. */
export interface ExportShape {
  /** The master switch. Off means no appendices at all. */
  appendix: boolean
  /** Whether the per-member statements appendix is included. */
  statements: boolean
}

export const BODY_SECTIONS: readonly BodySectionDefinition[] = [
  {
    id: 'overview',
    titleKey: 'overview.title',
    navKey: 'nav.overview',
  },
  {
    id: 'members',
    titleKey: 'members.title',
    navKey: 'nav.members',
    hintKey: 'members.hint',
  },
  {
    id: 'settle',
    titleKey: 'settle.title',
    navKey: 'nav.settle',
    hintKey: 'settle.hint',
    subsections: [
      { id: 'pool', titleKey: 'pool.title' },
      { id: 'transfers', titleKey: 'settlement.simplifiedTitle' },
    ],
  },
  {
    id: 'categories',
    titleKey: 'categories.title',
    navKey: 'nav.categories',
    hintKey: 'categories.hint',
    subsections: [
      { id: 'categoryTotals', titleKey: 'categories.totalsTitle' },
      { id: 'categoryByMember', titleKey: 'categories.byMemberTitle' },
    ],
    // The whole block is conditional, title and charts and nav entry together. A bill with
    // a category column that is empty in every row gets no empty chart; see
    // `hasCategories`, which is what this asks.
    when: (context) => context.categories,
  },
  {
    id: 'details',
    titleKey: 'details.title',
    navKey: 'nav.details',
    hintKey: 'details.hint',
    screenHintKey: 'details.hintScreen',
    checking: true,
  },
] as const

/**
 * The checking tables, in the order they are shown and lettered.
 *
 * `screenTitleKey` and `printTitleKey` differ only for `statements`, where the screen
 * shows one member at a time and the paper shows all of them -- the same content under
 * honestly different names.
 */
export interface CheckingDefinition {
  id: CheckingId
  screenTitleKey: string
  printTitleKey: string
  /** Whether this appendix is part of a given export. */
  included: (options: ExportShape) => boolean
}

export const CHECKING_SECTIONS: readonly CheckingDefinition[] = [
  {
    id: 'lending',
    screenTitleKey: 'settlement.realTitle',
    printTitleKey: 'settlement.realTitle',
    included: (options) => options.appendix,
  },
  {
    id: 'statements',
    screenTitleKey: 'details.statementsTitle',
    printTitleKey: 'appendix.statementsTitle',
    // The one appendix that is off by default. On the real bill it is seven tables of a
    // hundred-odd rows each, saying what the allocation appendix already says grouped
    // another way.
    included: (options) => options.appendix && options.statements,
  },
  {
    id: 'allocation',
    screenTitleKey: 'appendix.allocation',
    printTitleKey: 'appendix.allocation',
    included: (options) => options.appendix,
  },
  {
    id: 'sheet',
    screenTitleKey: 'appendix.sheet',
    printTitleKey: 'appendix.sheet',
    included: (options) => options.appendix,
  },
] as const

/** A body section with its number worked out. */
export interface ResolvedSection {
  id: BodySectionId
  /** 1-based, from the order of the visible sections. */
  number: number
  titleKey: string
  navKey: string
  hintKey?: string
  screenHintKey?: string
  printHintKey?: string
  /** Visible subsections, numbered `number.1`, `number.2`, ... */
  subsections: ResolvedSubsection[]
}

export interface ResolvedSubsection {
  id: string
  /** "3.1", assembled from the parent's number and this one's position. */
  label: string
  titleKey: string
}

/** An appendix with its letter worked out. */
export interface ResolvedAppendix {
  id: CheckingId
  /** "A", "B", ... from the order of the *included* appendices. */
  letter: string
  titleKey: string
}

export interface ResolvedStructure {
  medium: 'screen' | 'print'
  body: ResolvedSection[]
  /** Empty on screen, where the checking tables are subsections of `details` instead. */
  appendices: ResolvedAppendix[]
}

/** A..Z, then AA.. -- which no report will reach, but a wrong letter is worse than a
 *  long one. */
function letterFor(index: number): string {
  let label = ''
  let value = index
  do {
    label = String.fromCharCode(65 + (value % 26)) + label
    value = Math.floor(value / 26) - 1
  } while (value >= 0)
  return label
}

/**
 * Work out what renders and what it is called.
 *
 * One function for both media, because the alternative is two lists that agree until they
 * do not. What differs is where the checking tables land: subsections of `details` on
 * screen, lettered appendices on paper, and on paper `details` itself is not a body
 * section at all.
 */
export function resolve(
  medium: 'screen' | 'print',
  report: ReportShape,
  options: ExportShape,
): ResolvedStructure {
  const checking = CHECKING_SECTIONS.filter((entry) => entry.included(options))

  const visible = BODY_SECTIONS.filter((definition) => {
    if (definition.when && !definition.when(report)) return false
    // On paper the checking section becomes the appendices, so it is not numbered here.
    // With every appendix excluded there is nothing to point at either.
    if (definition.checking) return medium === 'screen' && checking.length > 0
    return true
  })

  const body = visible.map((definition, index) => {
    const number = index + 1
    const subsections = definition.checking
      ? checking.map((entry) => ({ id: entry.id, titleKey: entry.screenTitleKey }))
      : [...(definition.subsections ?? [])]
    return {
      id: definition.id,
      number,
      titleKey: definition.titleKey,
      navKey: definition.navKey,
      hintKey: definition.hintKey,
      screenHintKey: definition.screenHintKey,
      printHintKey: definition.printHintKey,
      subsections: subsections.map((entry, position) => ({
        id: entry.id,
        label: `${number}.${position + 1}`,
        titleKey: entry.titleKey,
      })),
    }
  })

  return {
    medium,
    body,
    appendices:
      medium === 'print'
        ? checking.map((entry, index) => ({
            id: entry.id,
            letter: letterFor(index),
            titleKey: entry.printTitleKey,
          }))
        : [],
  }
}

/** One body section of a resolved structure, or undefined if it does not render. */
export function bodySection(
  structure: ResolvedStructure,
  id: BodySectionId,
): ResolvedSection | undefined {
  return structure.body.find((entry) => entry.id === id)
}

/** One subsection, by its parent and its own id. */
export function subsection(
  structure: ResolvedStructure,
  parent: BodySectionId,
  id: string,
): ResolvedSubsection | undefined {
  return bodySection(structure, parent)?.subsections.find((entry) => entry.id === id)
}

export function appendix(
  structure: ResolvedStructure,
  id: CheckingId,
): ResolvedAppendix | undefined {
  return structure.appendices.find((entry) => entry.id === id)
}

/** The print view's anchor for anything with an id. */
export function printId(id: string): string {
  return `print-${id}`
}

/**
 * How the prose cites a checking table, or null when this export has none.
 *
 * The whole reason this is a function. On screen the target is a numbered subsection and
 * on paper a lettered appendix, so a hard-coded "see 5.1" is wrong in one medium and a
 * hard-coded "see Appendix A" is wrong in the other -- and both are wrong the moment an
 * export excludes something and the letters shift. Null means the target is not in this
 * export, and the caller omits the sentence rather than printing a dead link: §2.2's rule
 * that no appendix is silently made mandatory to keep a reference alive.
 *
 * The returned text names the thing as well as its number, because on paper "see Appendix
 * A" beside no hyperlink still has to tell the reader what they are looking for.
 */
export function crossRef(
  structure: ResolvedStructure,
  id: CheckingId,
  translate: (key: string, params?: Record<string, string | number>) => string,
): { label: string; anchor: string } | null {
  if (structure.medium === 'print') {
    const found = appendix(structure, id)
    if (!found) return null
    return {
      label: translate('ref.appendix', {
        letter: found.letter,
        title: translate(found.titleKey),
      }),
      anchor: printId(id),
    }
  }
  const found = subsection(structure, 'details', id)
  if (!found) return null
  return {
    label: translate('ref.section', {
      number: found.label,
      title: translate(found.titleKey),
    }),
    anchor: id,
  }
}

/**
 * A sentence with a cross-reference in the middle of it, split around the reference.
 *
 * The printed report links its references, so the reference has to be an `<a>` inside the
 * sentence rather than interpolated text. Vue cannot put a component into a translated
 * string, and the alternatives are both bad: `v-html` on translated text, or splitting the
 * sentence into two keys that a translator has to keep in an order the grammar may not want.
 *
 * So the placeholder stays in one translatable sentence and this splits the rendered string
 * on it. A translation that omits `{ref}` yields the whole sentence and an empty tail, which
 * loses the link rather than the text.
 */
export function aroundRef(
  message: string,
): { before: string; after: string } {
  const at = message.indexOf('{ref}')
  if (at < 0) return { before: message, after: '' }
  return { before: message.slice(0, at), after: message.slice(at + '{ref}'.length) }
}

/**
 * The standfirst for one section in one medium.
 *
 * The shared sentences, then the one this medium adds, if any. Assembled here rather than
 * in each component so that a section which gains a medium-specific sentence does not need
 * both views edited -- and so that neither view can quietly drop the shared part.
 */
export function sectionHint(
  section: ResolvedSection | undefined,
  medium: 'screen' | 'print',
  translate: (key: string) => string,
): string {
  if (!section?.hintKey) return ''
  const extra = medium === 'screen' ? section.screenHintKey : section.printHintKey
  return [section.hintKey, extra]
    .filter((key): key is string => Boolean(key))
    .map(translate)
    .join(' ')
}

/**
 * How the member table's figures relate, as bullets rather than as a paragraph.
 *
 * Shared by both views verbatim: these are the definitions the table's columns mean, and
 * two copies would drift. The two formulas are the point of the list -- `paid - consumed`
 * and `covered for - covered by` are the same number, and a reader who checks either has
 * checked the report rather than trusted it.
 *
 * Plain text on purpose. Not a tooltip and not behind a help icon: paper has no hover, and
 * a definition a printed report cannot state is a definition it does not have.
 */
export const MEMBER_TABLE_NOTES: readonly string[] = [
  'members.explainConsumed',
  'members.explainPaid',
  'members.explainCoveredFor',
  'members.explainCoveredBy',
  'members.formulaPaid',
  'members.formulaCovered',
  'members.explainSign',
] as const
