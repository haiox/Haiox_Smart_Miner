from setuptools import setup, find_packages

setup(
    name='haiox-smart-miner',
    version='2.0.0',
    package_dir={'': 'src'},
    packages=find_packages(where='src'),
    install_requires=[
        'httpx>=0.27.0',
        'beautifulsoup4>=4.12.0',
        'markdownify>=1.0.0',
        'pydantic>=2.0.0',
    ],
)
