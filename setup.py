from setuptools import setup, find_packages

# 讀取 requirements.txt
with open('requirements.txt') as f:
    requirements = f.read().splitlines()

# 讀取 README.md (如果存在)
try:
    with open('README.md', 'r', encoding='utf-8') as f:
        long_description = f.read()
except FileNotFoundError:
    long_description = 'WGC Screenshot Library - A Python wrapper for Windows Graphics Capture API to capture window screenshots'

setup(
    name='wgc-screenshot',
    version='1.0.0',
    author='4Games',
    author_email='',
    description='A Python library for capturing window screenshots using Windows Graphics Capture (WGC) API',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/4Games/screenshot_lib/WGC',
    packages=find_packages(),
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: Microsoft :: Windows',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Topic :: Software Development :: Libraries',
        'Topic :: Multimedia :: Graphics :: Capture',
    ],
    python_requires='>=3.8',
    install_requires=requirements,
    keywords='screenshot, windows, graphics, capture, WGC, window',
    project_urls={
        'Source': 'https://github.com/4Games/screenshot_lib/WGC',
        'Tracker': 'https://github.com/4Games/screenshot_lib/WGC/issues',
    },
)