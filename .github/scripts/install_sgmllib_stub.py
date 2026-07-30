#!/usr/bin/env python3
# @domain:   spec-1
# @module:   install_sgmllib_stub
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Install a minimal sgmllib stub so feedparser can be installed without sgmllib3k.

feedparser 6.x depends on sgmllib3k (released 2013), which fails to build
with modern pip/setuptools. This script:
  1. Writes a minimal sgmllib.py to site-packages (satisfies runtime import)
  2. Creates a fake sgmllib3k dist-info (satisfies pip's package resolver)

After this script runs, `pip install feedparser` (or any package that depends
on feedparser) will skip building sgmllib3k entirely.
"""
import os
import sys
import sysconfig

STUB = """\
import re
from html.parser import HTMLParser

interesting = re.compile("[&<]")
incomplete = re.compile("&([a-zA-Z][a-zA-Z0-9]*|#[0-9]*)")
entityref = re.compile("&([a-zA-Z][-.a-zA-Z0-9]*)[^a-zA-Z0-9]")
charref = re.compile("&#([0-9]+)[^0-9]")
starttagopen = re.compile("<[>a-zA-Z]")
shorttagopen = re.compile("<[a-zA-Z][a-zA-Z0-9.-]*/")
shorttag = re.compile("<([a-zA-Z][a-zA-Z0-9.-]*)/([^/]*)//")
piclose = re.compile(">")
endbracket = re.compile("[<>]")


class SGMLParser(HTMLParser):
    def __init__(self, verbose=0):
        super().__init__(convert_charrefs=False)

    def handle_entityref(self, name):
        pass

    def handle_charref(self, name):
        pass

    def handle_starttag(self, tag, attrs):
        m = getattr(self, "start_" + tag, None) or getattr(self, "do_" + tag, None)
        if m:
            m(attrs)
        else:
            self.unknown_starttag(tag, attrs)

    def handle_endtag(self, tag):
        m = getattr(self, "end_" + tag, None)
        if m:
            m()
        else:
            self.unknown_endtag(tag)

    def unknown_starttag(self, tag, attrs):
        pass

    def unknown_endtag(self, tag):
        pass
"""

DIST_INFO_METADATA = """\
Metadata-Version: 2.1
Name: sgmllib3k
Version: 1.0.0
Summary: Stub provided by install_sgmllib_stub.py
"""

DIST_INFO_RECORD = "sgmllib.py,,\n"

# sysconfig.get_paths()['purelib'] is the most reliable way to get the
# current interpreter's site-packages: works in system Python, venvs, and
# GitHub Actions toolcache Python where site.getsitepackages() may return
# a different (system) path than where pip actually installs.
site_dir = sysconfig.get_paths()["purelib"]

os.makedirs(site_dir, exist_ok=True)
print(f"[sgmllib stub] site_dir={site_dir}", file=sys.stderr)

# 1. Write sgmllib.py module
stub_path = os.path.join(site_dir, "sgmllib.py")
with open(stub_path, "w") as f:
    f.write(STUB)
print(f"[sgmllib stub] wrote {stub_path}", file=sys.stderr)

# 2. Create fake dist-info so pip's resolver sees sgmllib3k as installed
dist_info_dir = os.path.join(site_dir, "sgmllib3k-1.0.0.dist-info")
os.makedirs(dist_info_dir, exist_ok=True)

for fname, content in [
    ("METADATA", DIST_INFO_METADATA),
    ("INSTALLER", "pip\n"),
    ("RECORD", DIST_INFO_RECORD),
]:
    with open(os.path.join(dist_info_dir, fname), "w") as f:
        f.write(content)

print(f"[sgmllib stub] created {dist_info_dir}", file=sys.stderr)
