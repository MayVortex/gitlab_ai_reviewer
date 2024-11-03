from setuptools import find_packages, setup

# Read the contents of your README file
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="gitlab_ai_reviewer",
    version="0.1.0",
    author="Igor Reno",
    author_email="mayvortex@gmail.com",
    description="An automated (based on ChatGPT API) GitLab review helper with Telegram bot integration",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/MayVortex/gitlab_ai_reviewer",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    include_package_data=True,  # Includes files specified in MANIFEST.in
    install_requires=[
        "python-dotenv>=0.19.0",
        "python-gitlab",
        "python-telegram-bot>=20.0",
        "openai>=0.12.0",
        "gitpython>=3.1.24",
        "tiktoken",
        "pydantic",
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache2.0",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
    entry_points={
        "console_scripts": [
            "gitlab_ai_reviewer_start=main:main",
            "gitlab_ai_reviewer_bot=bots.tg_bot:main",
        ],
    },
)

