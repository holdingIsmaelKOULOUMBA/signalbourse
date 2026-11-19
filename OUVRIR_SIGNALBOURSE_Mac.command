#!/bin/bash
cd "$(dirname "$0")"
python3 -m pip install -r requirements.txt --quiet --disable-pip-version-check
python3 signal_bourse.py app
