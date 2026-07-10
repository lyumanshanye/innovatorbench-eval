#!/usr/bin/env python3
"""
Generate individual HTML pages for each rubric metric from markdown files.
Uses only Python standard library - no external packages required.
"""

import os
import re
import html as html_module

# Paths
RUBRIC_DIR = "/inspire/qb-ilm/project/qproject-fundationmodel/public/yelv_eval/fine_grained_eval/rubrics"
OUTPUT_DIR = "/inspire/qb-ilm/project/qproject-fundationmodel/public/yelv_eval/fine_grained_eval/present/rubrics"

# Create output directory
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Rubric files to process
RUBRIC_FILES = [
    "rubric_j06_error_recovery.md",
    "rubric_j13_cross_stage_violations.md",
    "rubric_j25_effective_action_ratio.md",
    "rubric_j30_parameter_accuracy.md",
    "rubric_j32_traj_satisfy.md",
    "rubric_j35_root_cause.md",
    "rubric_j37_propagation_length.md",
    "rubric_j39_failure_pattern.md",
    "rubric_j40_error_solidification.md",
    "rubric_j41_error_type_solidification.md",
    "rubric_j42_cat_failure.md",
    "rubric_j47_step_precision.md",
    "rubric_j48_step_recall.md",
    "rubric_j49_step_f1.md",
    "rubric_j50_evidence_action_gap.md",
    "rubric_j60_interaction_precision.md",
    "rubric_j63_hedging_frequency.md",
    "rubric_j64_uncertainty_calibration.md",
    "rubric_j65_question_quality.md",
    "rubric_j66_feedback_execution.md",
    "rubric_j68_feedback_utilization.md",
    "rubric_j70_hypothesis_verify.md",
    "rubric_j73_dual_channel_divergence.md",
    "rubric_j95_subtask_propagation.md",
]


def escape_html(text):
    """Escape HTML special characters."""
    return html_module.escape(text)


def parse_inline(text):
    """Convert inline markdown to HTML (bold, inline code, links)."""
    # Escape HTML first, but we'll handle code spans specially
    # Process code spans first (to avoid escaping inside them)
    parts = []
    pos = 0
    # Find all backtick code spans
    for m in re.finditer(r'`([^`]+)`', text):
        # Add text before this match (with inline formatting)
        before = text[pos:m.start()]
        parts.append(_format_inline_text(escape_html(before)))
        # Add the code span
        parts.append(f'<code>{escape_html(m.group(1))}</code>')
        pos = m.end()
    # Add remaining text
    remaining = text[pos:]
    parts.append(_format_inline_text(escape_html(remaining)))
    return ''.join(parts)


def _format_inline_text(text):
    """Apply bold, italic, and link formatting to already-escaped text."""
    # Bold: **text**
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # Italic: *text* (but not inside **)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    # Links: [text](url)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    return text


def markdown_to_html(md_content):
    """Convert markdown content to HTML."""
    lines = md_content.split('\n')
    html_parts = []
    i = 0
    in_table = False
    in_list = False
    list_type = None  # 'ul' or 'ol'

    while i < len(lines):
        line = lines[i]

        # Code blocks
        if line.strip().startswith('```'):
            lang = line.strip()[3:].strip()
            lang_class = f' class="language-{lang}"' if lang else ''
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i])
                i += 1
            code_content = escape_html('\n'.join(code_lines))
            html_parts.append(f'<div class="code-block"><pre><code{lang_class}>{code_content}</code></pre></div>')
            i += 1
            continue

        # Close table if we're leaving table context
        if in_table and not line.strip().startswith('|'):
            html_parts.append('</tbody></table></div>')
            in_table = False

        # Close list if we're leaving list context
        if in_list and not re.match(r'^(\s*[-*+]|\s*\d+\.)\s', line) and line.strip() != '':
            html_parts.append(f'</{list_type}>')
            in_list = False
            list_type = None

        # Headings
        if line.startswith('####'):
            html_parts.append(f'<h4>{parse_inline(line[4:].strip())}</h4>')
        elif line.startswith('###'):
            html_parts.append(f'<h3>{parse_inline(line[3:].strip())}</h3>')
        elif line.startswith('##'):
            html_parts.append(f'<h2>{parse_inline(line[2:].strip())}</h2>')
        elif line.startswith('#'):
            # Skip H1 - we'll use our own header
            pass

        # Table rows
        elif line.strip().startswith('|'):
            cells = [c.strip() for c in line.strip().split('|')[1:-1]]
            # Check if this is a separator row
            if all(re.match(r'^[-:]+$', c) for c in cells):
                i += 1
                continue
            if not in_table:
                in_table = True
                # This is the header row
                header_html = ''.join(f'<th>{parse_inline(c)}</th>' for c in cells)
                html_parts.append(f'<div class="table-wrapper"><table><thead><tr>{header_html}</tr></thead><tbody>')
            else:
                row_html = ''.join(f'<td>{parse_inline(c)}</td>' for c in cells)
                html_parts.append(f'<tr>{row_html}</tr>')

        # Unordered list items
        elif re.match(r'^(\s*)[-*+]\s', line):
            if not in_list:
                in_list = True
                list_type = 'ul'
                html_parts.append('<ul>')
            content = re.sub(r'^\s*[-*+]\s', '', line)
            html_parts.append(f'<li>{parse_inline(content)}</li>')

        # Ordered list items
        elif re.match(r'^\s*\d+\.\s', line):
            if not in_list or list_type != 'ol':
                if in_list:
                    html_parts.append(f'</{list_type}>')
                in_list = True
                list_type = 'ol'
                html_parts.append('<ol>')
            content = re.sub(r'^\s*\d+\.\s', '', line)
            html_parts.append(f'<li>{parse_inline(content)}</li>')

        # Horizontal rule
        elif re.match(r'^---+$', line.strip()):
            html_parts.append('<hr>')

        # Empty line
        elif line.strip() == '':
            if in_list:
                html_parts.append(f'</{list_type}>')
                in_list = False
                list_type = None
            pass  # skip blank lines

        # Paragraph
        else:
            # Collect consecutive non-empty, non-special lines as a paragraph
            para_lines = [line]
            while (i + 1 < len(lines) and
                   lines[i + 1].strip() != '' and
                   not lines[i + 1].startswith('#') and
                   not lines[i + 1].strip().startswith('|') and
                   not lines[i + 1].strip().startswith('```') and
                   not re.match(r'^(\s*[-*+]|\s*\d+\.)\s', lines[i + 1]) and
                   not re.match(r'^---+$', lines[i + 1].strip())):
                i += 1
                para_lines.append(lines[i])
            html_parts.append(f'<p>{parse_inline(" ".join(para_lines))}</p>')

        i += 1

    # Close any open structures
    if in_table:
        html_parts.append('</tbody></table></div>')
    if in_list:
        html_parts.append(f'</{list_type}>')

    return '\n'.join(html_parts)


def extract_metric_info(filename, md_content):
    """Extract metric ID and name from filename and content."""
    # From filename: rubric_j06_error_recovery.md -> j06, error_recovery
    match = re.match(r'rubric_(j\d+)_(.+)\.md', filename)
    if match:
        metric_id = match.group(1).upper()
        metric_slug = match.group(2)
        metric_name = metric_slug.replace('_', ' ').title()
    else:
        metric_id = "J??"
        metric_slug = "unknown"
        metric_name = "Unknown Metric"

    # Try to get a better name from the H1 heading
    h1_match = re.match(r'^#\s+(.+)$', md_content, re.MULTILINE)
    if h1_match:
        h1_text = h1_match.group(1).strip()
        # Remove the "J06 — " prefix if present to get the descriptive name
        name_match = re.match(r'J\d+\s*[—\-]\s*(.+?)(?:\s*Rubric)?$', h1_text)
        if name_match:
            metric_name = name_match.group(1).strip()
            # Remove trailing " — Evaluation Rubric" or similar
            metric_name = re.sub(r'\s*[—\-]\s*Evaluation\s*Rubric\s*$', '', metric_name)
            metric_name = re.sub(r'\s*Rubric\s*$', '', metric_name)

    return metric_id, metric_slug, metric_name


def generate_html_page(metric_id, metric_slug, metric_name, body_html):
    """Generate a complete standalone HTML page."""
    output_filename = f"{metric_id.lower()}_{metric_slug}.html"

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{metric_id} - {escape_html(metric_name)}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {{
            --navy: #0f2440;
            --accent: #2563eb;
            --gold: #d97706;
            --green: #059669;
            --bg: #fafbfc;
            --text: #1e293b;
            --text-muted: #64748b;
            --border: #e2e8f0;
            --card-bg: #ffffff;
            --code-bg: #1e1e2e;
            --code-text: #cdd6f4;
            --score-1: #dc2626;
            --score-2: #ea580c;
            --score-3: #d97706;
            --score-4: #65a30d;
            --score-5: #059669;
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.7;
            font-size: 15px;
        }}

        .page-header {{
            background: linear-gradient(135deg, var(--navy) 0%, #1a365d 100%);
            color: white;
            padding: 2.5rem 2rem;
            position: relative;
            overflow: hidden;
        }}

        .page-header::before {{
            content: '';
            position: absolute;
            top: -50%;
            right: -10%;
            width: 400px;
            height: 400px;
            background: radial-gradient(circle, rgba(37, 99, 235, 0.15) 0%, transparent 70%);
            border-radius: 50%;
        }}

        .header-content {{
            max-width: 900px;
            margin: 0 auto;
            position: relative;
            z-index: 1;
        }}

        .back-link {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            color: rgba(255, 255, 255, 0.7);
            text-decoration: none;
            font-size: 0.85rem;
            font-weight: 500;
            margin-bottom: 1.5rem;
            transition: color 0.2s;
        }}

        .back-link:hover {{
            color: white;
        }}

        .back-link svg {{
            width: 16px;
            height: 16px;
        }}

        .metric-badge {{
            display: inline-block;
            background: var(--accent);
            color: white;
            font-size: 0.8rem;
            font-weight: 600;
            padding: 0.3rem 0.75rem;
            border-radius: 4px;
            letter-spacing: 0.5px;
            margin-bottom: 0.75rem;
        }}

        .page-header h1 {{
            font-size: 1.8rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            margin-bottom: 0.5rem;
        }}

        .scoring-scale {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.5rem;
            margin: 2rem auto;
            max-width: 900px;
        }}

        .scoring-scale h3 {{
            font-size: 0.85rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-muted);
            margin-bottom: 1rem;
        }}

        .scale-bar {{
            display: flex;
            gap: 4px;
            margin-bottom: 0.5rem;
        }}

        .scale-step {{
            flex: 1;
            height: 8px;
            border-radius: 4px;
            position: relative;
        }}

        .scale-step:nth-child(1) {{ background: var(--score-1); }}
        .scale-step:nth-child(2) {{ background: var(--score-2); }}
        .scale-step:nth-child(3) {{ background: var(--score-3); }}
        .scale-step:nth-child(4) {{ background: var(--score-4); }}
        .scale-step:nth-child(5) {{ background: var(--score-5); }}

        .scale-labels {{
            display: flex;
            justify-content: space-between;
            font-size: 0.75rem;
            color: var(--text-muted);
            padding: 0 0.25rem;
        }}

        .scale-labels span {{
            text-align: center;
        }}

        .scale-details {{
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 8px;
            margin-top: 1rem;
        }}

        .scale-detail {{
            text-align: center;
            padding: 0.5rem 0.25rem;
            border-radius: 6px;
            font-size: 0.7rem;
            line-height: 1.4;
            background: var(--bg);
        }}

        .scale-detail .num {{
            font-weight: 700;
            font-size: 1.1rem;
            display: block;
            margin-bottom: 0.25rem;
        }}

        .scale-detail:nth-child(1) .num {{ color: var(--score-1); }}
        .scale-detail:nth-child(2) .num {{ color: var(--score-2); }}
        .scale-detail:nth-child(3) .num {{ color: var(--score-3); }}
        .scale-detail:nth-child(4) .num {{ color: var(--score-4); }}
        .scale-detail:nth-child(5) .num {{ color: var(--score-5); }}

        .content {{
            max-width: 900px;
            margin: 0 auto;
            padding: 2rem;
        }}

        .content h2 {{
            font-size: 1.35rem;
            font-weight: 700;
            color: var(--navy);
            margin: 2.5rem 0 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 2px solid var(--border);
        }}

        .content h3 {{
            font-size: 1.1rem;
            font-weight: 600;
            color: var(--text);
            margin: 1.75rem 0 0.75rem;
        }}

        .content h4 {{
            font-size: 0.95rem;
            font-weight: 600;
            color: var(--text-muted);
            margin: 1.25rem 0 0.5rem;
        }}

        .content p {{
            margin-bottom: 1rem;
            color: var(--text);
        }}

        .content ul, .content ol {{
            margin: 0.75rem 0 1rem 1.5rem;
        }}

        .content li {{
            margin-bottom: 0.4rem;
            padding-left: 0.25rem;
        }}

        .content li::marker {{
            color: var(--accent);
        }}

        .content strong {{
            font-weight: 600;
            color: var(--navy);
        }}

        .content code {{
            font-family: 'JetBrains Mono', monospace;
            background: #f1f5f9;
            padding: 0.15rem 0.4rem;
            border-radius: 4px;
            font-size: 0.85em;
            color: #be185d;
        }}

        .code-block {{
            margin: 1.25rem 0;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        }}

        .code-block pre {{
            background: var(--code-bg);
            padding: 1.25rem 1.5rem;
            overflow-x: auto;
            margin: 0;
        }}

        .code-block code {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.8rem;
            line-height: 1.6;
            color: var(--code-text);
            background: none;
            padding: 0;
            border-radius: 0;
        }}

        .table-wrapper {{
            overflow-x: auto;
            margin: 1.25rem 0;
            border-radius: 10px;
            border: 1px solid var(--border);
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
        }}

        thead {{
            background: var(--navy);
            color: white;
        }}

        th {{
            padding: 0.75rem 1rem;
            text-align: left;
            font-weight: 600;
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.3px;
        }}

        td {{
            padding: 0.75rem 1rem;
            border-top: 1px solid var(--border);
            vertical-align: top;
        }}

        tbody tr:hover {{
            background: #f8fafc;
        }}

        hr {{
            border: none;
            border-top: 2px solid var(--border);
            margin: 2rem 0;
        }}

        .footer {{
            text-align: center;
            padding: 2rem;
            margin-top: 3rem;
            border-top: 1px solid var(--border);
        }}

        .footer a {{
            color: var(--accent);
            text-decoration: none;
            font-weight: 500;
            font-size: 0.9rem;
        }}

        .footer a:hover {{
            text-decoration: underline;
        }}

        @media (max-width: 768px) {{
            .page-header {{
                padding: 1.5rem 1rem;
            }}

            .page-header h1 {{
                font-size: 1.4rem;
            }}

            .content {{
                padding: 1.5rem 1rem;
            }}

            .scale-details {{
                grid-template-columns: repeat(5, 1fr);
                gap: 4px;
            }}

            .scale-detail {{
                font-size: 0.6rem;
                padding: 0.4rem 0.1rem;
            }}

            .table-wrapper {{
                font-size: 0.8rem;
            }}

            th, td {{
                padding: 0.5rem;
            }}
        }}

        @media (max-width: 480px) {{
            .scale-details {{
                grid-template-columns: 1fr;
                gap: 6px;
            }}

            .scale-detail {{
                display: flex;
                align-items: center;
                gap: 0.5rem;
                text-align: left;
                padding: 0.5rem 0.75rem;
            }}

            .scale-detail .num {{
                margin-bottom: 0;
                min-width: 1.5rem;
            }}
        }}
    </style>
</head>
<body>
    <header class="page-header">
        <div class="header-content">
            <a href="../index.html#metrics" class="back-link">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="15 18 9 12 15 6"></polyline>
                </svg>
                Back to Overview
            </a>
            <div class="metric-badge">{metric_id}</div>
            <h1>{escape_html(metric_name)}</h1>
        </div>
    </header>

    <div class="scoring-scale">
        <h3>Scoring Scale (1-5)</h3>
        <div class="scale-bar">
            <div class="scale-step"></div>
            <div class="scale-step"></div>
            <div class="scale-step"></div>
            <div class="scale-step"></div>
            <div class="scale-step"></div>
        </div>
        <div class="scale-labels">
            <span>1 - Worst</span>
            <span>2</span>
            <span>3 - Mid</span>
            <span>4</span>
            <span>5 - Best</span>
        </div>
        <div class="scale-details">
            <div class="scale-detail"><span class="num">1</span> Poor / None</div>
            <div class="scale-detail"><span class="num">2</span> Below Average</div>
            <div class="scale-detail"><span class="num">3</span> Moderate</div>
            <div class="scale-detail"><span class="num">4</span> Good</div>
            <div class="scale-detail"><span class="num">5</span> Excellent</div>
        </div>
    </div>

    <main class="content">
        {body_html}
    </main>

    <footer class="footer">
        <a href="../index.html#metrics">&#8592; Back to Metrics Overview</a>
    </footer>
</body>
</html>'''
    return output_filename, html


def main():
    generated = []
    errors = []

    for filename in RUBRIC_FILES:
        filepath = os.path.join(RUBRIC_DIR, filename)
        if not os.path.exists(filepath):
            errors.append(f"File not found: {filepath}")
            continue

        with open(filepath, 'r', encoding='utf-8') as f:
            md_content = f.read()

        # Extract metric info
        metric_id, metric_slug, metric_name = extract_metric_info(filename, md_content)

        # Convert markdown to HTML (skip the H1 line since we use our own header)
        body_html = markdown_to_html(md_content)

        # Generate HTML page
        output_filename, html_content = generate_html_page(metric_id, metric_slug, metric_name, body_html)
        output_path = os.path.join(OUTPUT_DIR, output_filename)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        generated.append(output_filename)
        print(f"  Generated: {output_filename}")

    print(f"\nDone! Generated {len(generated)} HTML pages in {OUTPUT_DIR}")
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors:
            print(f"  - {e}")


if __name__ == "__main__":
    main()
