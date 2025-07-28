import pdfplumber, statistics, re
from pathlib import Path

NUM_PAT = re.compile(r"^(?P<num>([0-9]+(\.[0-9]+)*|[IVXLCDM]+|第[一二三四五六七八九十百千]+章))\\b")
HEADER_TOL_Y = 10  # px tolerance for header/footer repeat detection


def process_pdf(pdf_path):
    """Process a PDF and return a dict with title and outline."""
    with pdfplumber.open(pdf_path) as pdf:
        all_lines = []
        for p_idx, page in enumerate(pdf.pages, start=1):
            lines = extract_lines(page, p_idx)
            all_lines.extend(lines)

    lines = drop_repeating_headers(all_lines)
    lines = merge_wrapped_heading_lines(lines)

    scored = score_lines(lines)
    cands = [l for l in scored if l["score"] >= scored_threshold(scored)]

    title = detect_title(pdf_path, scored, cands)
    outline = assign_levels(cands)

    return {"title": title, "outline": outline}


def extract_lines(page, page_num):
    """Extract lines from a pdfplumber page with font and layout metadata. Returns list of line dicts."""
    # Get all words (pdfplumber's word extraction is robust for most PDFs)
    words = page.extract_words(extra_attrs=["fontname", "size"])
    if not words:
        return []

    # Group words into lines by y0 (top) with a tolerance
    y_tol = 2.5  # points; adjust as needed
    lines = []
    current_line = []
    last_y = None
    for w in sorted(words, key=lambda w: (w['top'], w['x0'])):
        if last_y is None or abs(w['top'] - last_y) <= y_tol:
            current_line.append(w)
            last_y = w['top'] if last_y is None else (last_y + w['top']) / 2
        else:
            lines.append(current_line)
            current_line = [w]
            last_y = w['top']
    if current_line:
        lines.append(current_line)

    # Compute features for each line
    line_dicts = []
    prev_bottom = None
    for line in lines:
        text = " ".join(w['text'] for w in line).strip()
        font_names = [w.get('fontname', '') for w in line]
        font_sizes = [float(w.get('size', 0)) for w in line]
        x0 = min(w['x0'] for w in line)
        x1 = max(w['x1'] for w in line)
        top = min(w['top'] for w in line)
        bottom = max(w['bottom'] for w in line)
        is_boldish = any('Bold' in fn or 'bold' in fn or 'Black' in fn for fn in font_names)
        is_all_caps = text.isupper() and len(text) > 2
        avg_font_size = sum(font_sizes) / len(font_sizes) if font_sizes else 0
        leading = (top - prev_bottom) if prev_bottom is not None else 0
        indent = x0 - min(w['x0'] for w in words)  # relative to leftmost word on page
        prev_bottom = bottom
        line_dicts.append({
            "page": page_num,
            "text": text,
            "font_names": font_names,
            "font_sizes": font_sizes,
            "x0": x0,
            "x1": x1,
            "top": top,
            "bottom": bottom,
            "is_boldish": is_boldish,
            "is_all_caps": is_all_caps,
            "avg_font_size": avg_font_size,
            "leading": leading,
            "indent": indent
        })
    return line_dicts


def drop_repeating_headers(lines):
    """Remove lines that appear as headers/footers on most pages."""
    # TODO: Implement header/footer detection
    return lines


def merge_wrapped_heading_lines(lines):
    """Merge lines that are likely part of the same heading split across lines."""
    # TODO: Implement line merging
    return lines


def score_lines(lines):
    """Score each line for heading likelihood using multi-signal heuristics. Returns list of dicts with 'score'."""
    if not lines:
        return []
    # Compute page median font size for z-score
    font_sizes = [l["avg_font_size"] for l in lines if l["avg_font_size"] > 0]
    if not font_sizes:
        font_sizes = [10.0]  # fallback
    median_size = statistics.median(font_sizes)
    stdev_size = statistics.stdev(font_sizes) if len(font_sizes) > 1 else 1.0
    # Compute median line spacing (leading)
    leadings = [l["leading"] for l in lines if l["leading"] > 0]
    median_leading = statistics.median(leadings) if leadings else 0
    # For indent, get leftmost x0 as margin
    min_x0 = min(l["x0"] for l in lines)
    # Score each line
    for l in lines:
        score = 0.0
        size_z = (l["avg_font_size"] - median_size) / stdev_size if stdev_size else 0
        score += size_z * 2.0
        if l["is_boldish"]:
            score += 1.0
        len_tokens = len(l["text"].split())
        if 5 < len_tokens < 25:
            score += 1.0
        elif len_tokens <= 5:
            score -= 0.25
        # Numbering pattern
        if NUM_PAT.match(l["text"]):
            score += 1.5
        # Gap above (leading)
        gap_above_ratio = l["leading"] / median_leading if median_leading and l["leading"] else 1.0
        if gap_above_ratio > 1.5:
            score += 0.75
        # Ends with colon
        if l["text"].rstrip().endswith(":"):
            score += 0.25
        # All caps
        if l["is_all_caps"]:
            score += 0.5
        # Indent pattern
        if abs(l["indent"]) < 5:
            score += 0.5
        # Page 1, top 25%
        if l["page"] == 1 and l["top"] < (page_height_hint(l) * 0.25):
            score += 1.0
        l["score"] = score
    return lines


def scored_threshold(scored):
    """Compute adaptive threshold for heading candidate selection."""
    scores = [l["score"] for l in scored]
    if not scores:
        return 0
    mean = statistics.mean(scores)
    stdev = statistics.stdev(scores) if len(scores) > 1 else 0
    return mean + stdev


def detect_title(pdf_path, scored, cands):
    """Detect the document title using heuristics and PDF metadata."""
    # 1. Try PDF metadata
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            meta_title = (pdf.metadata or {}).get("Title", "")
    except Exception:
        meta_title = ""
    meta_title = meta_title.strip() if meta_title else ""
    if meta_title and any(meta_title.lower() in l["text"].lower() for l in scored[:20]):
        return " ".join(meta_title.split())
    # 2. Highest-scoring heading on page 1
    page1 = [l for l in cands if l["page"] == 1]
    if page1:
        best = max(page1, key=lambda l: l["score"])
        if best["score"] > 0:
            return " ".join(best["text"].split())
    # 3. First large centered line on page 1
    page1_lines = [l for l in scored if l["page"] == 1]
    if page1_lines:
        page_width = max((l["x1"] for l in page1_lines), default=600)
        for l in page1_lines:
            center = abs((l["x0"] + l["x1"]) / 2 - page_width / 2)
            if l["avg_font_size"] > statistics.median([x["avg_font_size"] for x in page1_lines]) and center < page_width * 0.15:
                return " ".join(l["text"].split())
    # 4. Fallback: first H1 candidate
    if cands:
        return " ".join(cands[0]["text"].split())
    return None

def assign_levels(cands):
    """Assign H1/H2/H3 levels to heading candidates and return outline list."""
    if not cands:
        return []
    # Cluster font sizes (k=3 or unique sizes)
    sizes = sorted(set(l["avg_font_size"] for l in cands))
    if len(sizes) >= 3:
        thresholds = [sizes[-1], sizes[-2], sizes[-3]]
    else:
        thresholds = sizes[::-1] + [sizes[0]] * (3 - len(sizes))
    def font_level(size):
        if size >= thresholds[0]:
            return 1
        elif size >= thresholds[1]:
            return 2
        else:
            return 3
    # Numbering depth
    def numbering_level(text):
        m = NUM_PAT.match(text)
        if m:
            num = m.group("num")
            if "." in num:
                return min(num.count(".") + 1, 3)
            elif any(c in num for c in "一二三四五六七八九十百千"):
                return 1  # treat as H1 for kanji
            else:
                return 1
        return None
    # Assign levels
    outline = []
    seen = set()
    for l in cands:
        f_level = font_level(l["avg_font_size"])
        n_level = numbering_level(l["text"])
        level = min(f_level, n_level) if n_level else f_level
        # Indent tiebreaker
        if level > 1 and l["indent"] > 10:
            level = min(level + 1, 3)
        # Remove duplicates (same text, page, y)
        key = (l["text"].strip(), l["page"], round(l["top"]))
        if key in seen:
            continue
        seen.add(key)
        outline.append({
            "level": f"H{level}",
            "text": l["text"].strip(),
            "page": l["page"]
        })
    # Guarantee at least one H1
    if not any(o["level"] == "H1" for o in outline) and outline:
        outline[0]["level"] = "H1"
    # Demote isolated H3s
    for i, o in enumerate(outline):
        if o["level"] == "H3" and not any(p["level"] == "H2" for p in outline[:i]):
            o["level"] = "H2"
    return outline

def page_height_hint(line):
    """Estimate page height from line's top/bottom (for title boost)."""
    # This is a fallback; ideally, pass page height from pdfplumber
    return max(line["bottom"] + 50, 792)  # 792pt = 11in page 