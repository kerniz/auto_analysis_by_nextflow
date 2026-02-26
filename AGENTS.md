# AGENTS.md - Guidelines for Coding Agents

This document provides build/lint/test commands and code style guidelines for agents working in this Nextflow bioinformatics pipeline repository.

## Build/Lint/Test Commands

### Nextflow Pipeline
```bash
# Run the complete pipeline
nextflow run main.nf

# Run with specific profile (docker/singularity/apptainer)
nextflow run main.nf -profile docker

# Run with custom parameters
nextflow run main.nf --pubmed_id 12345678 --outdir ./custom_results

# Test individual processes
nextflow run main.nf -process.pubmed_search
nextflow run main.nf -process.type_detection
nextflow run main.nf -process.data_download
nextflow run main.nf -process.analysis

# Validate pipeline syntax
nextflow lint main.nf

# Clean execution cache
nextflow clean -f
```

### Python Scripts
```bash
# Test individual Python components
python3 pubmed_search.py 40315330
python3 type_detection.py GSE291599
python3 download_script.py

# Python syntax checking
python3 -m py_compile pubmed_search.py
python3 -m py_compile type_detection.py
python3 -m py_compile download_script.py
```

### Docker Environment
```bash
# Build Docker image
docker build -t opencode:latest .

# Run with docker-compose
docker-compose up --build

# Execute in container
docker-compose run opencode bash
```

## Code Style Guidelines

### Nextflow (.nf files)
- Use DSL-2 syntax (`nextflow.enable.dsl=2`)
- Process names should be snake_case and descriptive
- Input/output declarations should be clearly typed
- Script blocks use bash syntax with proper quoting
- Parameter declarations in `nextflow.config` not main script
- Include error handling and exit codes in scripts
- Use profile-based container configuration

### Python Scripts
- Imports: standard library first, then third-party
- Use `sys.stderr` for error messages, `sys.exit(1)` for failures
- Functions should be snake_case with descriptive names
- Include `if __name__ == "__main__":` guard clauses
- Use f-strings for string formatting
- Add type hints where beneficial
- Handle HTTP requests with proper error checking

### File Organization
- Main pipeline: `main.nf`
- Configuration: `nextflow.config`
- Python utilities: `*_script.py` or `*.py` with descriptive names
- Docker: `Dockerfile` and `docker-compose.yml`
- Results: output to `./results` or specified `--outdir`

### Error Handling
- Python scripts should exit with code 1 on errors
- Use stderr for error messages, stdout for results
- Nextflow processes should handle missing inputs gracefully
- Include validation for critical parameters (PubMed IDs, GSE IDs)

### Naming Conventions
- Files: snake_case (e.g., `pubmed_search.py`)
- Nextflow processes: snake_case (e.g., `pubmed_search`)
- Variables: snake_case, descriptive names
- Constants: UPPER_SNAKE_CASE
- Functions: snake_case, verb-based (e.g., `search_pubmed`)

### Documentation
- Include shebang `#!/usr/bin/env nextflow` or `#!/usr/bin/env python3`
- Add inline comments for complex logic
- Document parameter purposes in config files
- Include usage examples in script docstrings

### Container Best Practices
- Use official base images (ubuntu:24.04)
- Set `DEBIAN_FRONTEND=noninteractive` for apt
- Clean up apt caches (`rm -rf /var/lib/apt/lists/*`)
- Mount workspace directory properly
- Include necessary tools in Dockerfile

## Pipeline Architecture

This is a 4-stage bioinformatics pipeline:
1. **PubMed Search**: Extract GEO dataset IDs from PubMed records
2. **Type Detection**: Determine analysis type (scRNA-seq, etc.) from metadata
3. **Data Download**: Fetch FASTQ files using SRA Toolkit
4. **Analysis**: Run appropriate nf-core pipeline based on data type

## Testing Strategy

- Test each Python script independently before pipeline integration
- Use known PubMed ID (40315330) for end-to-end testing
- Verify output file formats (datasets.txt, analysis_type.txt, samplesheet.csv)
- Check container execution with different profiles
- Validate SRA download and FASTQ file generation

## Dependencies

- Nextflow (>=22.10.x)
- Python 3 with requests library
- SRA Toolkit (prefetch, fastq-dump)
- Docker/Singularity/Apptainer for containerization
- nf-core/scrnaseq pipeline for analysis