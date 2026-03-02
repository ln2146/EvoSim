#!/bin/bash
cd "/Users/LN/Desktop/new_Evocorps"
export TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=1
"/Users/LN/anaconda3/envs/MOSAIC/bin/python" "src/start_database_service.py"
echo
read -p "Press any key to exit..."
