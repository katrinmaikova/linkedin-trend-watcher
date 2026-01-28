from setuptools import setup, find_packages

setup(
    name="linkedin_trend_watcher",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "flexus-client-kit",
        "httpx",
        "beautifulsoup4",
        "lxml",
    ],
    package_data={"": ["*.webp", "*.png", "*.html", "*.lark", "*.json"]},
)
