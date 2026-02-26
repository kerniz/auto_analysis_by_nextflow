#!/usr/bin/env nextflow

nextflow.enable.dsl=2

params.pubmed_id = '40315330'
params.outdir = './results'

// Process 1: PubMed search and dataset extraction
process pubmed_search {
    input:
    val pmid

    output:
    path 'datasets.txt', emit: datasets

    script:
    """
    python3 -c "
from pubmed_client import PubMedClient
client = PubMedClient()
metadata = client.fetch_paper_metadata('${pmid}')
geo_links = metadata.get('geo_links', []) if metadata else []
for link in geo_links:
    print(link)
" > datasets.txt
    """
}

// Process 2: Type detection from paper metadata
process type_detection {
    input:
    path datasets
    val pmid

    output:
    path 'analysis_type.txt', emit: analysis_type

    script:
    """
    python3 -c "
from pubmed_client import PubMedClient
from sequencing_detector import SequencingDetector
client = PubMedClient()
metadata = client.fetch_paper_metadata('${pmid}')
detector = SequencingDetector()
result = detector.detect_sequencing_type(metadata or {})
print(result.get('sequencing_type', 'unknown'))
" > analysis_type.txt
    """
}

// Process 3: Data download using SRA Toolkit
process data_download {
    input:
    path datasets
    val pmid

    output:
    path 'fastq', emit: fastq_dir
    path 'samplesheet.csv', emit: samplesheet

    script:
    """
    python3 -c "
from sra_explorer import SRAExplorer
explorer = SRAExplorer()
with open('${datasets}') as f:
    sra_links = [line.strip() for line in f if line.strip()]
result = explorer.explore_sra_datasets('${pmid}', sra_links)
srr_ids = []
for ds in result.get('datasets', []):
    srr_ids.extend(ds.get('runs', []))
with open('sra_ids.txt', 'w') as f:
    for sid in srr_ids:
        f.write(sid + '\n')
"
    # Download FASTQ
    mkdir -p fastq
    for srr in \$(cat sra_ids.txt); do
        prefetch \$srr
        fastq-dump --gzip --split-files --outdir fastq \$srr
    done
    # Generate samplesheet
    echo "sample,fastq_1,fastq_2" > samplesheet.csv
    find fastq -name "*_1.fastq.gz" | while read f; do
        sample=\$(basename \$f | sed 's/_1.fastq.gz//')
        fq2=\${f/_1.fastq.gz/_2.fastq.gz}
        echo "\${sample},\${PWD}/\${f},\${PWD}/\${fq2}" >> samplesheet.csv
    done
    """
}

// Process 4: Analysis using nf-core pipelines
process analysis {
    input:
    path samplesheet
    path analysis_type

    output:
    path 'analysis_results', emit: results

    script:
    """
    type=\$(cat ${analysis_type})
    if [ "\${type}" == "scrnaseq" ]; then
        nextflow run nf-core/scrnaseq -r 4.0.0 \
            --input ${samplesheet} \
            --outdir analysis_results \
            --protocol 10xv3 \
            -profile singularity
    elif [ "\${type}" == "rnaseq" ]; then
        nextflow run nf-core/rnaseq -r 3.14.0 \
            --input ${samplesheet} \
            --outdir analysis_results \
            -profile singularity
    else
        mkdir -p analysis_results
        echo "Unsupported analysis type: \${type}" > analysis_results/error.txt
    fi
    """
}

workflow {
    datasets = pubmed_search(params.pubmed_id)
    analysis_type = type_detection(datasets, params.pubmed_id)
    (fastq_dir, samplesheet) = data_download(datasets, params.pubmed_id)
    results = analysis(samplesheet, analysis_type)

    results.view()
}
