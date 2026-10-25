# SPEC-1 Module Canonical Audit

Generated: 2026-06-17 18:49 UTC

## cls_leads

### Commit History
- Canonical `src/cls_leads`: **7 commits**, last: `be2962d 2026-06-14 chore: promote cls_* namespaces to gh_main`
- Orphan `src/spec1_analytics/cls_leads`: **2 commits**, last: `ac15fd6 2026-06-14 chore: seed @domain tags across repo`

### File Comparison

| file | canonical lines | orphan lines | diff lines | identical? |
|------|-----------------|--------------|------------|------------|
| formatter.py | 99 | 99 | 12
0 | DIFFERS |
| generator.py | 137 | 137 | 12
0 | DIFFERS |
| __init__.py | 1 | 1 | 4
0 | DIFFERS |
| schemas.py | 58 | 58 | 10
0 | DIFFERS |
| store.py | 111 | 111 | 12
0 | DIFFERS |

✓ No orphan-only files — canonical tree contains everything orphan has.

### Test Imports
- Tests importing `cls_leads`: **10 files**
- Tests importing `spec1_analytics.cls_leads`: **6 files**

### Production Import Usage
- Other `src/` files importing canonical pattern: **15**
- Other `src/` files importing orphan pattern: **7**

### Verdict
✓ Canonical tree is correctly the more-imported version. Orphan is safe to retire after migrating remaining 7 references.

---

## cls_psyop

### Commit History
- Canonical `src/cls_psyop`: **9 commits**, last: `be2962d 2026-06-14 chore: promote cls_* namespaces to gh_main`
- Orphan `src/spec1_analytics/cls_psyop`: **3 commits**, last: `ac15fd6 2026-06-14 chore: seed @domain tags across repo`

### File Comparison

| file | canonical lines | orphan lines | diff lines | identical? |
|------|-----------------|--------------|------------|------------|
| evidence.py | 88 | 88 | 10
0 | DIFFERS |
| __init__.py | 1 | 1 | 4
0 | DIFFERS |
| patterns.py | 215 | 215 | 12
0 | DIFFERS |
| pipeline.py | 533 | 113 | 506
0 | DIFFERS |
| schemas.py | 77 | 77 | 10
0 | DIFFERS |
| scorer.py | 98 | 98 | 14
0 | DIFFERS |
| store.py | 109 | 109 | 12
0 | DIFFERS |

✓ No orphan-only files — canonical tree contains everything orphan has.

### Test Imports
- Tests importing `cls_psyop`: **18 files**
- Tests importing `spec1_analytics.cls_psyop`: **9 files**

### Production Import Usage
- Other `src/` files importing canonical pattern: **33**
- Other `src/` files importing orphan pattern: **15**

### Verdict
✓ Canonical tree is correctly the more-imported version. Orphan is safe to retire after migrating remaining 15 references.

---

## cls_world_brief

### Commit History
- Canonical `src/cls_world_brief`: **5 commits**, last: `be2962d 2026-06-14 chore: promote cls_* namespaces to gh_main`
- Orphan `src/spec1_analytics/cls_world_brief`: **5 commits**, last: `ac15fd6 2026-06-14 chore: seed @domain tags across repo`

### File Comparison

| file | canonical lines | orphan lines | diff lines | identical? |
|------|-----------------|--------------|------------|------------|
| formatter.py | 106 | 106 | 12
0 | DIFFERS |
| __init__.py | 1 | 1 | 4
0 | DIFFERS |
| producer.py | 143 | 143 | 12
0 | DIFFERS |
| schemas.py | 67 | 67 | 10
0 | DIFFERS |
| store.py | 123 | 123 | 14
0 | DIFFERS |

**Files existing ONLY in orphan tree (review for lost functionality):**
- `synthetic.py`

### Test Imports
- Tests importing `cls_world_brief`: **7 files**
- Tests importing `spec1_analytics.cls_world_brief`: **6 files**

### Production Import Usage
- Other `src/` files importing canonical pattern: **28**
- Other `src/` files importing orphan pattern: **17**

### Verdict
✓ Canonical tree is correctly the more-imported version. Orphan is safe to retire after migrating remaining 17 references.

---

