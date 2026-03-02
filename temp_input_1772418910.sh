#!/bin/bash
cd "/Users/LN/Desktop/new_Evocorps"
export TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=1
{
  printf "%s\n" "y"
  printf "%s\n" "y"
  printf "%s\n" "n"
  printf "%s\n" "n"
  printf "%s\n" ""
} | "/Users/LN/anaconda3/envs/MOSAIC/bin/python" "src/main.py"
echo
read -p "Press any key to exit..."
