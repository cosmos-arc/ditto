#!/usr/bin/env python
"""Coverage report viewer and analysis tool."""

import argparse
import subprocess
import webbrowser
import xml.etree.ElementTree as ET
from pathlib import Path

# Coverage threshold constant
COVERAGE_THRESHOLD = 0.8


def open_html_report() -> None:
    """Open HTML coverage report in browser."""
    html_file = Path("htmlcov/index.html")
    if html_file.exists():
        print(f"Opening coverage report: {html_file.absolute()}")
        webbrowser.open(f"file://{html_file.absolute()}")
    else:
        print("HTML coverage report not found. Run with --generate first.")


def generate_coverage_report() -> bool:
    """Generate coverage report."""
    print("Generating coverage report...")

    # Run pytest with coverage
    cmd = [
        "pixi",
        "run",
        "python",
        "-m",
        "pytest",
        "--cov=packages/",
        "--cov-report=html",
        "--cov-report=term-missing",
        "--cov-report=xml",
        "--cov-fail-under=0",  # Don't fail on low coverage
        "-v",
    ]

    result = subprocess.run(cmd, check=False, capture_output=True, text=True)

    if result.returncode == 0:
        print("\n✅ Coverage report generated successfully!")
        print("\n📊 Summary:")
        # Extract coverage summary from output
        lines = result.stdout.split("\n")
        for line in lines:
            if "TOTAL" in line:
                print(f"   {line.strip()}")
    else:
        print("\n❌ Failed to generate coverage report")
        print(result.stderr)

    return result.returncode == 0


def show_coverage_summary() -> None:
    """Show coverage summary from XML report."""
    xml_file = Path("coverage.xml")
    if not xml_file.exists():
        print("No coverage.xml found. Run with --generate first.")
        return

    tree = ET.parse(xml_file)
    root = tree.getroot()

    # Get overall coverage
    coverage = root.attrib.get("line-rate", "0")
    coverage_pct = float(coverage) * 100

    print(f"\n📊 Overall Coverage: {coverage_pct:.2f}%")

    # Find files with low coverage
    low_coverage_files: list[tuple[str, float]] = []
    for package in root.findall(".//package"):
        for classes in package.findall("classes"):
            for cls in classes.findall("class"):
                class_name = cls.attrib.get("name", "")
                line_rate = float(cls.attrib.get("line-rate", 0))
                if line_rate < COVERAGE_THRESHOLD:
                    low_coverage_files.append((class_name, line_rate))

    if low_coverage_files:
        print(f"\n⚠️  Files with low coverage (<{COVERAGE_THRESHOLD * 100:.0f}%):")
        for file_name, coverage_float in sorted(low_coverage_files, key=lambda x: x[1]):
            print(f"   {file_name}: {coverage_float * 100:.1f}%")


def check_specific_file(file_path: str) -> None:
    """Check coverage for a specific file."""
    xml_file = Path("coverage.xml")
    if not xml_file.exists():
        print("No coverage.xml found. Run with --generate first.")
        return

    tree = ET.parse(xml_file)
    root = tree.getroot()

    # Look for the file
    for classes in root.findall(".//classes"):
        for cls in classes.findall("class"):
            class_name = cls.attrib.get("name", "")
            if file_path in class_name or class_name.endswith(file_path):
                line_rate = float(cls.attrib.get("line-rate", 0))
                lines_covered = int(cls.attrib.get("lines-covered", 0))
                lines_valid = int(cls.attrib.get("lines-valid", 0))

                print(f"\n📄 Coverage for {class_name}:")
                print(f"   Coverage: {line_rate * 100:.2f}%")
                print(f"   Lines: {lines_covered}/{lines_valid}")

                # Show uncovered lines
                lines = cls.findall(".//line")
                uncovered = []
                for line in lines:
                    if line.attrib.get("hits") == "0":
                        uncovered.append(int(line.attrib.get("number", 0)))

                if uncovered:
                    print(f"   Uncovered lines: {uncovered}")
                return

    print(f"File {file_path} not found in coverage report.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Coverage report viewer")
    parser.add_argument(
        "--generate", action="store_true", help="Generate coverage report"
    )
    parser.add_argument(
        "--open", action="store_true", help="Open HTML report in browser"
    )
    parser.add_argument("--summary", action="store_true", help="Show coverage summary")
    parser.add_argument("--check", type=str, help="Check coverage for specific file")
    parser.add_argument(
        "--all", action="store_true", help="Generate, show summary, and open report"
    )

    args = parser.parse_args()

    if args.all:
        generate_coverage_report()
        show_coverage_summary()
        open_html_report()
    elif args.generate:
        generate_coverage_report()
    elif args.open:
        open_html_report()
    elif args.summary:
        show_coverage_summary()
    elif args.check:
        check_specific_file(args.check)
    else:
        print("Coverage Report Viewer")
        print("\nUsage:")
        print("  python view_coverage.py --generate     Generate coverage report")
        print("  python view_coverage.py --open         Open HTML report")
        print("  python view_coverage.py --summary      Show coverage summary")
        print("  python view_coverage.py --check FILE   Check specific file")
        print("  python view_coverage.py --all          Generate + summary + open")
