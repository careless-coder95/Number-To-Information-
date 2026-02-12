#!/usr/bin/env bash
# Build script for Render

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright and Chromium
echo "Installing Playwright browsers..."
export PLAYWRIGHT_BROWSERS_PATH=/opt/render/project/src/browsers
playwright install chromium
# on Render, install-deps might fail without sudo, but we try it
# playwright install-deps  <-- preventing failure explicitly if sudo missing, usually chromium runs fine on standard images

