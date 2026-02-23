#!/bin/bash
# Test script for the biomni container image
# Usage: bash test_image.sh /path/to/sandbox_or_sif

IMAGE="${1:?Usage: bash test_image.sh /path/to/image}"

echo "=== Testing image: $IMAGE ==="

# Use -W for writable-tmpfs to avoid bind mount issues (project, scratch, etc.)
EXEC="apptainer exec -W /tmp -c $IMAGE"

echo ""
echo "--- Conda environment ---"
$EXEC conda info --envs

echo ""
echo "--- Python packages ---"
$EXEC python -c '
import sys
print("Python:", sys.version)
pkgs = {
    "numpy": "numpy", "pandas": "pandas", "scipy": "scipy",
    "sklearn": "sklearn", "scanpy": "scanpy", "Bio": "biopython",
    "matplotlib": "matplotlib", "seaborn": "seaborn",
    "networkx": "networkx", "transformers": "transformers",
    "langchain": "langchain", "openai": "openai",
    "gradio": "gradio", "rdkit": "rdkit",
    "cv2": "opencv", "statsmodels": "statsmodels",
}
for imp, name in pkgs.items():
    try:
        __import__(imp)
        print(f"  OK: {name}")
    except ImportError:
        print(f"  MISSING: {name}")
'

echo ""
echo "--- R packages ---"
$EXEC Rscript -e '
pkgs <- c("ggplot2","dplyr","tidyr","readr","stringr","DESeq2","edgeR",
          "limma","lme4","WGCNA","Rgraphviz","flowCore","clusterProfiler",
          "dada2","xcms","Rcpp","devtools","harmony","Matrix")
for (p in pkgs) {
  if (require(p, character.only=TRUE, quietly=TRUE))
    cat("  OK:", p, "\n")
  else
    cat("  MISSING:", p, "\n")
}
'

echo ""
echo "--- Conda bioinformatics tools ---"
$EXEC bash -c 'for tool in samtools bowtie2 bwa bedtools fastqc mafft blastn mageck; do if command -v $tool &>/dev/null; then echo "  OK: $tool"; else echo "  MISSING: $tool"; fi; done'

echo ""
echo "--- Standalone CLI tools ---"
$EXEC bash -c 'for tool in plink2 iqtree2 gcta64 FastTree muscle; do if command -v $tool &>/dev/null; then echo "  OK: $tool"; else echo "  MISSING: $tool"; fi; done'

echo ""
echo "--- Directory structure ---"
$EXEC bash -c 'echo "  /workspace: $(test -d /workspace && echo exists || echo missing)"; echo "  /opt/conda/envs/biomni_e1: $(test -d /opt/conda/envs/biomni_e1 && echo exists || echo missing)"; echo "  /opt/biomni_tools/bin: $(test -d /opt/biomni_tools/bin && echo exists || echo missing)"'

echo ""
echo "=== Test complete ==="
