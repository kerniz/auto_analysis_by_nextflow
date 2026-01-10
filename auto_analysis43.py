import sys

def download_sra_data(pmid):
    # 기존 코드 유지

def run_nfcore_rnaseq(sra_file_path, output_dir):
    # rnaseq 파이프라인 실행 코드 유지

def run_llm_analysis(nfcore_output_dir, llm_url):
    # 기존 코드 유지

def enrichr_pathway_analysis(llm_results):
    # 기존 코드 유지

def run_sarek(sra_file_path, output_dir):
    # sarek 파이프라인 실행 코드 추가
    pass

def run_naseq(sra_file_path, output_dir):
    # naseq 파이프라인 실행 코드 추가
    pass

def run_scrnaseq(sra_file_path, output_dir):
    # scrnaseq 파이프라인 실행 코드 추가
    pass

def run_metagenome(sra_file_path, output_dir):
    # metagenome 파이프라인 실행 코드 추가
    pass

def main(pmid, llm_url="http://localhost:11434"):
    sra_file_path = download_sra_data(pmid)
    nfcore_output_dir = run_nfcore_rnaseq(sra_file_path, output_dir)
    run_llm_analysis(nfcore_output_dir, llm_url)
    enrichr_pathway_analysis(llm_results)

    # 추가 파이프라인 실행
    run_sarek(sra_file_path, output_dir)
    run_naseq(sra_file_path, output_dir)
    run_scrnaseq(sra_file_path, output_dir)
    run_metagenome(sra_file_path, output_dir)

if __name__ == '__main__':
    main(sys.argv[1])
