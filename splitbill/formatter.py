"""
Table formatter for displaying transaction results.
"""

import pandas as pd
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


def format_transaction_table(df, currency=None):
    """
    Format transaction DataFrame into a beautiful table string.
    
    Args:
        df: DataFrame with columns [Creditor, Debtor, Amount]
        currency: Optional currency code to display
    
    Returns:
        Formatted table string
    """
    if df.empty:
        return "No transactions needed - everyone is settled!"
    
    # Get column names from DataFrame
    col_creditor = df.columns[0]
    col_debtor = df.columns[1]
    col_amount = df.columns[2]
    
    # Prepare data with Transaction ID
    rows = []
    for idx, row in df.iterrows():
        transaction_id = idx + 1  # Start from 1 instead of 0
        creditor = str(row[col_creditor])
        debtor = str(row[col_debtor])
        # Format amount with thousand separators
        amount = f"{row[col_amount]:,.2f}"
        rows.append((str(transaction_id), creditor, "<--", debtor, amount))

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
        stats: Mapping of member name to `loader.MemberStats`. Rendered in the
            order given.
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