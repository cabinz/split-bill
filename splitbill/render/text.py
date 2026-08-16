"""
Table formatter for displaying transaction results.
"""

import unicodedata


def get_display_width(text):
    """
    Calculate the display width of a string.
    Chinese characters and other wide characters count as 2, others as 1.
    """
    if text is None:
        return 0
    
    width = 0
    for char in str(text):
        # Check if character is East Asian Wide or Fullwidth
        if unicodedata.east_asian_width(char) in ['W', 'F']:
            width += 2
        else:
            width += 1
    return width


def pad_string(text, target_width, align='left'):
    """
    Pad a string to target display width, considering wide characters.
    
    Args:
        text: String to pad
        target_width: Target display width
        align: 'left', 'right', or 'center'
    """
    text = str(text) if text is not None else ''
    current_width = get_display_width(text)
    padding_needed = target_width - current_width
    
    if padding_needed <= 0:
        return text
    
    if align == 'left':
        return text + ' ' * padding_needed
    elif align == 'right':
        return ' ' * padding_needed + text
    else:  # center
        left_pad = padding_needed // 2
        right_pad = padding_needed - left_pad
        return ' ' * left_pad + text + ' ' * right_pad


def render_box_table(headers, rows, aligns=None, min_content_widths=None,
                     fixed_widths=None):
    """Render rows into a box-drawing table.

    Args:
        headers: Header label of each column.
        rows: Sequence of rows, each a sequence of already-stringified cells.
        aligns: Data-cell alignment per column ('left'/'right'/'center').
            Headers are always centered. Defaults to all centered.
        min_content_widths: Minimum width of each column's content, applied
            before the gutters are added. Defaults to 0 for every column.
        fixed_widths: Final width of each column, gutters included, bypassing
            measurement. Use None for a column that should be measured.

    Returns:
        Formatted table string.
    """
    n_cols = len(headers)
    aligns = aligns or ['center'] * n_cols
    min_content_widths = min_content_widths or [0] * n_cols
    fixed_widths = fixed_widths or [None] * n_cols

    # Each column fits its widest cell (or its header), plus a one-space gutter
    # on either side. Cells are aligned within the gutters, so that neither a
    # left- nor a right-aligned cell ends up touching a border.
    GUTTER = 1
    widths = []
    for i in range(n_cols):
        if fixed_widths[i] is not None:
            widths.append(fixed_widths[i])
            continue
        content_width = max(
            [get_display_width(headers[i]), min_content_widths[i]]
            + [get_display_width(row[i]) for row in rows]
        )
        widths.append(content_width + 2 * GUTTER)

    # Box drawing characters
    top_left = "╔"
    top_right = "╗"
    bottom_left = "╚"
    bottom_right = "╝"
    horizontal = "═"
    vertical = "║"
    cross = "╬"
    t_down = "╦"
    t_up = "╩"
    t_right = "╠"
    t_left = "╣"

    def _border(left, joint, right):
        return left + joint.join(horizontal * w for w in widths) + right

    def _cell(text, width, align):
        gutter = ' ' * GUTTER
        return gutter + pad_string(text, width - 2 * GUTTER, align) + gutter

    def _row(cells, cell_aligns):
        return (vertical
                + vertical.join(_cell(cell, width, align)
                                for cell, width, align
                                in zip(cells, widths, cell_aligns))
                + vertical)

    lines = [
        _border(top_left, t_down, top_right),
        _row(headers, ['center'] * n_cols),
        _border(t_right, cross, t_left),
    ]
    lines.extend(_row(row, aligns) for row in rows)
    lines.append(_border(bottom_left, t_up, bottom_right))

    return '\n'.join(lines)


def format_transaction_table(transfers, col_amount="Amount"):
    """Format a settlement into a table string.

    Args:
        transfers: Sequence of `settle.Transfer`. Rendered in the order given.
        col_amount: Header for the amount column, currency suffix included.

    The arrow points from payer to payee: the "Debtor" column holds whoever sends
    the money. The columns keep the lending vocabulary the CLI has always used,
    even though a settlement counterparty is a by-product of re-pairing nets --
    changing that wording is a decision about the report, not about this refactor.

    Returns:
        Formatted table string.
    """
    if not transfers:
        return "No transactions needed - everyone is settled!"

    rows = [
        (
            str(idx + 1),
            str(transfer.receiver),
            "<--",
            str(transfer.sender),
            f"{transfer.amount:,.2f}",
        )
        for idx, transfer in enumerate(transfers)
    ]

    return render_box_table(
        headers=["#", "Creditor", "", "Debtor", col_amount],
        rows=rows,
        aligns=['center', 'center', 'center', 'center', 'right'],
        min_content_widths=[2, 0, 0, 0, 0],  # "#" header is 1 char
        fixed_widths=[None, None, 5, None, None],  # fixed arrow column
    )


def format_member_stats_table(stats, currency=None):
    """Format per-member spending statistics into a table string.

    Args:
        stats: Mapping of member name to anything carrying `consumption`, `paid`,
            `paid_for_others` and `net` -- a `loader.MemberStats` or a
            `report.Position`. Rendered in the order given, which is the caller's
            responsibility: the order carries meaning (net descending, so the
            people owed money come first) and this function does not second-guess
            it.
        currency: Optional currency code to display in the amount headers.

    Returns:
        Formatted table string.
    """
    if not stats:
        return "No members found."

    suffix = f" ({currency})" if currency else ""
    rows = [
        (
            name,
            f"{s.consumption:,.2f}",
            f"{s.paid:,.2f}",
            f"{s.paid_for_others:,.2f}",
            f"{s.net:+,.2f}",
        )
        for name, s in stats.items()
    ]

    return render_box_table(
        headers=[
            "Member",
            "Consumption" + suffix,
            "Paid" + suffix,
            "Paid for Others" + suffix,
            "Net" + suffix,
        ],
        rows=rows,
        aligns=['left', 'right', 'right', 'right', 'right'],
    )