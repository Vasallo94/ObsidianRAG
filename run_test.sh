#!/bin/bash
/Users/enriquebook/ObsidianRAG/.venv/bin/python test_links.py > debug_output.txt 2>&1
ls -l test_links_output.txt >> debug_output.txt 2>&1
