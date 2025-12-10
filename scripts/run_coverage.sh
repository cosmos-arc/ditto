#!/bin/bash

# Quick test runner with coverage
echo "🚀 Running tests with coverage..."
echo ""

# Run tests with detailed coverage
pixi run python -m pytest \
    --cov=packages/ \
    --cov-report=html:htmlcov \
    --cov-report=term-missing:skip-covered \
    --cov-report=xml:coverage.xml \
    --cov-branch \
    --cov-fail-under=0 \
    -v \
    "$@"

# Show result
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Tests passed!"
    echo ""
    echo "📊 Coverage reports generated:"
    echo "   - HTML: htmlcov/index.html"
    echo "   - XML: coverage.xml"
    echo ""
    echo "💡 Run 'python scripts/view_coverage.py --open' to view HTML report"
    echo "💡 Run 'python scripts/view_coverage.py --summary' for quick summary"
else
    echo ""
    echo "❌ Some tests failed"
    exit 1
fi
