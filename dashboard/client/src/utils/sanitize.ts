/**
 * Sanitize VLM descriptor text for clean display.
 * Handles common issues:
 * - Raw JSON output from the model
 * - Repetitive word/phrase loops
 * - Excessive length
 */
export function sanitizeDescriptor(raw: string | undefined | null): string {
  if (!raw || raw === 'normal') return '';

  let text = raw.trim();

  // 1. If the text looks like JSON, extract the meaningful field
  if (text.startsWith('{') || text.startsWith('```')) {
    // Strip markdown code fences
    text = text.replace(/^```\w*\s*/g, '').replace(/\s*```$/g, '');

    try {
      const obj = JSON.parse(text);
      // Try common keys the VLM might use
      const desc =
        obj.description ||
        obj.short_reason ||
        obj.event_type ||
        obj.reason ||
        obj.summary ||
        '';
      if (typeof desc === 'string' && desc.trim()) {
        text = desc.trim();
      }
    } catch {
      // Not valid JSON — try to extract from partial JSON
      const descMatch = text.match(/"(?:description|short_reason|reason|summary)"\s*:\s*"([^"]+)"/);
      if (descMatch) {
        text = descMatch[1].trim();
      } else {
        // Remove JSON syntax noise
        text = text
          .replace(/[{}"[\]]/g, ' ')
          .replace(/\b(event_type|severity_score|description|short_reason|confidence|risk_level|verdict)\b\s*:/gi, '')
          .replace(/\s+/g, ' ')
          .trim();
      }
    }
  }

  // 2. Collapse repetitive words/phrases (e.g., "robbery attempt robbery attempt robbery attempt")
  //    Split into words, detect repeating sequences
  const words = text.split(/\s+/);
  if (words.length > 6) {
    // Try detecting repeating n-grams (2-4 word phrases)
    for (let n = 2; n <= 4; n++) {
      if (words.length < n * 2) continue;
      const first = words.slice(0, n).join(' ');
      let repeats = 0;
      for (let i = 0; i <= words.length - n; i += n) {
        if (words.slice(i, i + n).join(' ') === first) {
          repeats++;
        } else {
          break;
        }
      }
      if (repeats >= 2) {
        // Deduplicate: keep just the phrase once
        text = first;
        break;
      }
    }

    // Also handle single-word repetition: "attempt attempt attempt"
    const uniqueConsec: string[] = [words[0]];
    let repeatCount = 1;
    for (let i = 1; i < words.length; i++) {
      if (words[i] === words[i - 1]) {
        repeatCount++;
        if (repeatCount > 2) continue; // skip after 2nd repetition
      } else {
        repeatCount = 1;
      }
      uniqueConsec.push(words[i]);
    }
    if (uniqueConsec.length < words.length) {
      text = uniqueConsec.join(' ');
    }
  }

  // 3. Strip pipe-separated lists (e.g., "theft|robbery|robbery attempt")
  if (text.includes('|')) {
    const parts = text.split('|').map(s => s.trim()).filter(Boolean);
    // Deduplicate
    const unique = [...new Set(parts)];
    text = unique.slice(0, 3).join(', ');
  }

  // 4. Removed length cap - allow components to use CSS truncation (e.g., line-clamp) as needed

  // 5. Capitalize first letter
  if (text.length > 0) {
    text = text.charAt(0).toUpperCase() + text.slice(1);
  }

  return text;
}
