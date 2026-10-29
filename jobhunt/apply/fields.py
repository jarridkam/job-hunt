"""Form field discovery and label -> profile mapping."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Runs inside the page (or an iframe). Tags every usable control with data-jh-idx and
# radio/checkbox groups with data-jh-group, and returns a JSON description of each control.
COLLECT_JS = r"""
() => {
  const isVisible = (el) => {
    const st = window.getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden') return false;
    if (el.getAttribute('aria-hidden') === 'true') return false;
    if (el.type === 'file' || el.type === 'checkbox' || el.type === 'radio') return true; // often visually hidden
    if (st.opacity === '0' || el.getAttribute('tabindex') === '-1') return false; // react-select companion inputs
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const sectionLabel = (el) => {
    // For file inputs: the nearest heading/label naming the section (Resume/CV, Cover Letter).
    let p = el.parentElement, depth = 0;
    while (p && depth < 7 && p.tagName !== 'FORM') {
      const cands = p.querySelectorAll('label, legend, h1, h2, h3, h4, h5, h6, [class*="label" i], [class*="heading" i], [class*="title" i]');
      for (const c of cands) { const t = textOf(c); if (/resume|résumé|\bcv\b|cover/i.test(t)) return t.slice(0, 120); }
      p = p.parentElement; depth++;
    }
    return '';
  };
  const textOf = (el) => (el ? (el.innerText || el.textContent || '') : '').replace(/\s+/g, ' ').trim();
  const ownLabel = (el) => {
    let parts = [];
    if (el.id) document.querySelectorAll(`label[for="${CSS.escape(el.id)}"]`).forEach(l => parts.push(textOf(l)));
    const lab = el.closest('label'); if (lab) parts.push(textOf(lab));
    const al = el.getAttribute('aria-label'); if (al) parts.push(al);
    const alb = el.getAttribute('aria-labelledby');
    if (alb) alb.split(/\s+/).forEach(id => { const n = document.getElementById(id); if (n) parts.push(textOf(n)); });
    const ph = el.getAttribute('placeholder'); if (ph) parts.push(ph);
    if (!parts.join('').trim()) {
      let p = el.parentElement, depth = 0;
      while (p && depth < 4) {
        const l = p.querySelector('label, legend, [class*="label" i], [class*="question" i]');
        if (l && textOf(l)) { parts.push(textOf(l)); break; }
        p = p.parentElement; depth++;
      }
    }
    return parts.filter(Boolean).join(' | ').slice(0, 300);
  };
  const optionLabel = (el) => {
    const lab = el.closest('label') || (el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`));
    const t = lab ? textOf(lab) : '';
    return t || el.value || '';
  };
  // Find the container that holds exactly this group of radios/checkboxes and its question text.
  const groupOf = (el) => {
    const type = el.type;
    let members = [];
    if (el.name) members = Array.from(document.querySelectorAll(`input[type="${type}"][name="${CSS.escape(el.name)}"]`));
    let anc = null;
    if (members.length > 1) {
      anc = el.parentElement;
      while (anc && anc.tagName !== 'FORM' && anc.querySelectorAll(`input[name="${CSS.escape(el.name)}"]`).length < members.length) anc = anc.parentElement;
    } else {
      // unnamed or uniquely named checkboxes: look for a nearby cluster
      let p = el.parentElement, depth = 0;
      while (p && depth < 4 && p.tagName !== 'FORM') {
        const boxes = Array.from(p.querySelectorAll(`input[type="${type}"]`));
        if (boxes.length >= 2 && boxes.length <= 20) { anc = p; members = boxes; break; }
        p = p.parentElement; depth++;
      }
    }
    if (!anc || anc.tagName === 'FORM' || members.length < 2) return null;
    const allInputs = anc.querySelectorAll('input, select, textarea').length;
    if (allInputs > members.length + 2) return null; // container is too broad to be "the question"
    let gl = '';
    const lg = anc.querySelector('legend');
    if (lg) gl = textOf(lg);
    if (!gl) {
      // first text line of the container that is not an option label
      const optTexts = new Set(members.map(optionLabel));
      const lines = textOf(anc).split(/\s{2,}|\n/);
      const full = (anc.innerText || '').split('\n').map(s => s.trim()).filter(Boolean);
      for (const ln of full) { if (!optTexts.has(ln)) { gl = ln; break; } }
    }
    return { anc, members, label: (gl || '').slice(0, 200) };
  };
  const out = [];
  let idx = 0, gid = 0;
  const groupIds = new Map();
  const els = document.querySelectorAll('input, textarea, select, [role="combobox"], [contenteditable="true"]');
  els.forEach(el => {
    if (['hidden', 'submit', 'button', 'image', 'reset'].includes(el.type)) return;
    if (!isVisible(el)) return;
    if (el.disabled || el.readOnly) return;
    el.setAttribute('data-jh-idx', String(idx));
    const tag = el.tagName.toLowerCase();
    let kind = tag === 'select' ? 'select' : tag === 'textarea' ? 'textarea' : (el.getAttribute('role') === 'combobox' ? 'combobox' : (el.getAttribute('contenteditable') === 'true' ? 'textarea' : (el.type || 'text')));
    let opts = tag === 'select' ? Array.from(el.options).map(o => o.text.trim()).filter(Boolean) : [];
    let group = null, groupLabel = '';
    if (kind === 'radio' || kind === 'checkbox') {
      const g = groupOf(el);
      if (g) {
        if (!groupIds.has(g.anc)) { groupIds.set(g.anc, 'g' + (gid++)); g.members.forEach(m => m.setAttribute('data-jh-group', groupIds.get(g.anc))); }
        group = groupIds.get(g.anc);
        groupLabel = g.label;
        opts = g.members.map(optionLabel).filter(Boolean);
      }
    }
    let lbl = ownLabel(el);
    if (kind === 'file') { const s = sectionLabel(el); if (s) lbl = s + ' | ' + lbl; }
    const required = el.required || el.getAttribute('aria-required') === 'true' || /\*/.test(lbl) || /\*/.test(groupLabel);
    out.push({ idx, kind, name: el.name || '', id: el.id || '', label: lbl, group_label: groupLabel, required, options: opts,
               value: el.value || '', group, autocomplete: el.getAttribute('autocomplete') || '' });
    idx++;
  });
  return out;
}
"""


@dataclass
class Field:
    idx: int
    kind: str
    name: str
    id: str
    label: str
    required: bool
    options: list[str] = field(default_factory=list)
    value: str = ""
    group: str | None = None
    group_label: str = ""
    autocomplete: str = ""

    @property
    def selector(self) -> str:
        return f'[data-jh-idx="{self.idx}"]'

    @property
    def group_selector(self) -> str:
        return f'[data-jh-group="{self.group}"]' if self.group else self.selector

    @property
    def question(self) -> str:
        """The text to classify against: the group's question for radios/checkboxes, else the own label."""
        if self.kind in ("radio", "checkbox") and self.group_label:
            return self.group_label
        return self.label

    @property
    def text(self) -> str:
        return f"{self.question} {self.name} {self.id} {self.autocomplete}".lower()

    @property
    def display(self) -> str:
        return (self.question or self.label or self.name or f"field {self.idx}")[:80]


RULES: list[tuple[str, re.Pattern]] = [
    ("first_name", re.compile(r"first\s*name|given\s*name|\bfname\b|given-name", re.I)),
    ("last_name", re.compile(r"last\s*name|surname|family\s*name|\blname\b|family-name", re.I)),
    ("full_name", re.compile(r"^(?:full\s*)?name\b|\bfull\s*name|your name|legal name", re.I)),
    ("email", re.compile(r"e-?mail", re.I)),
    ("phone", re.compile(r"phone|mobile|\btel\b", re.I)),
    ("pronouns", re.compile(r"pronoun", re.I)),
    ("hear_about", re.compile(r"how did you (?:hear|find|learn)|referral source|where did you (?:hear|find)|\bsource\b", re.I)),
    ("eeo", re.compile(r"gender|\bsex\b|race|ethnic|hispanic|latino|veteran|disabilit|military|sexual orientation|transgender|self[- ]identif", re.I)),
    ("linkedin", re.compile(r"linked\s*in", re.I)),
    ("github", re.compile(r"git\s*hub", re.I)),
    ("website", re.compile(r"portfolio|website|personal site|\burl\b|other link", re.I)),
    ("resume", re.compile(r"resume|résumé|\bcv\b|curriculum", re.I)),
    ("cover_letter", re.compile(r"cover\s*letter|letter of (?:interest|motivation)|why (?:do you want|are you interested)", re.I)),
    ("sponsorship", re.compile(r"sponsor|visa|immigration", re.I)),
    ("work_auth", re.compile(r"authori[sz]ed|legally (?:able|eligible|permitted)|eligible to work|right to work|work authorization|work permit", re.I)),
    ("optin", re.compile(r"opt[- ]?in|whatsapp|\bsms\b|text message|marketing (?:email|communication)", re.I)),
    ("years_experience", re.compile(r"years? of (?:\w+ ){0,3}experience|how many years", re.I)),
    ("salary", re.compile(r"salary|compensation|pay expectation|desired pay|rate expectation", re.I)),
    ("start_date", re.compile(r"start date|available to start|availability|notice period", re.I)),
    ("consent", re.compile(r"i (?:agree|consent|acknowledge|accept|confirm|certify|have read)|privacy (?:policy|notice)|\bterms\b|gdpr|data processing|keep my data|future opportunit", re.I)),
    ("degree", re.compile(r"degree|education level|highest level of education", re.I)),
    ("school", re.compile(r"school|university|college|institution", re.I)),
    ("location", re.compile(r"^location|location \(city\)|\bcity\b|where (?:are|do) you (?:based|live|located)|current location|\baddress\b", re.I)),
    ("current_company", re.compile(r"current (?:company|employer)", re.I)),
    ("current_title", re.compile(r"current (?:title|role|position)", re.I)),
]


def classify(f: Field) -> str:
    t = f.text
    if f.kind == "file":
        if re.search(r"cover", t):
            return "cover_letter"
        if re.search(r"resume|résumé|\bcv\b|curriculum", t):
            return "resume"
        if re.search(r"additional|other|supporting|attach|portfolio|transcript|writing sample|reference", t):
            return "unknown"  # optional extras: never re-upload the resume here
        return "resume"
    for key, pat in RULES:
        if pat.search(t):
            if key == "full_name" and re.search(r"first|last|company|school|employer|file|user", t):
                continue
            if key == "location" and re.search(r"email|phone|remote|relocat|\?", t):
                continue
            if key in ("linkedin", "github", "website") and f.kind in ("radio", "checkbox"):
                continue  # these are "how did you hear" options, not profile links
            return key
    return "unknown"
