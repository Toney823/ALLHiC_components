# Usage
## Prune
### Dependencies
* [htslib](https://github.com/samtools/htslib)
### Installation
This is a new version of ALLHiC_prune, for directly use
```bash
git clone https://github.com/sc-zhang/ALLHiC_components.git
cd Prune
chmod +x ALLHiC_prune
```

For build
```bash
git clone https://github.com/sc-zhang/ALLHiC_components.git
cd Prune

# with shared library "libhts.so"
export CPPFLAGS="-I/path/to/htslib/include"
export LDFLAGS="-L/path/to/htslib/lib"
make

# with static library "libhts.a"
wget https://github.com/samtools/htslib/releases/download/1.17/htslib-1.17.tar.bz2
tar jxvf htslib-1.17.tar.bz2
cd htslib-1.17
./configure ./configure --disable-libcurl
make
cd ..
g++ -O3 --std=c++11 -o ALLHiC_prune -I. -Ihtslib-1.17 ALLHiC_prune.cpp Prune.cpp htslib-1.17/libhts.a -lz -llzma -lbz2 -lpthread
```

If compiled with shared library "libhts.so" add the line below to .bashrc or .bash_profile
```bash
export LD_LIBRAYR_PATH="/path/to/htslib/lib/":$LD_LIBRARY_PATH
```

### Usage
```bash
************************************************************************
    Usage: ./ALLHiC_prune -i Allele.ctg.table -b sorted.bam
      -h : help and usage.
      -i : Allele.ctg.table
      -b : sorted.bam
************************************************************************
```
## Other scripts
### Dependencies
* pysam
* numpy
* matplotlib
* jcvi
* h5py
### Installation
```bash
git clone https://github.com/sc-zhang/ALLHiC_components.git
chmod +x *.py
chmod +x *.sh
```
### Usage
**partition_gmap.py** is used for spliting bam and contig level fasta by chromosomes with allele table.
```bash
usage: partition_gmap.py [-h] -r REF -g ALLELETABLE [-b BAM] [-d WORKDIR]
                         [-t THREAD]

optional arguments:
  -h, --help            show this help message and exit
  -r REF, --ref REF     reference contig level assembly
  -g ALLELETABLE, --alleletable ALLELETABLE
                        Allele.gene.table
  -b BAM, --bam BAM     bam file, default: prunning.bam
  -d WORKDIR, --workdir WORKDIR
                        work directory, default: wrk_dir
  -t THREAD, --thread THREAD
                        threads, default: 10
```

**ALLHiC_partition.py** is an **experimental** script for clustering contigs into haplotypes.
```bash
usage: ALLHiC_partition.py [-h] -r REF -b BAM -d BED -a ANCHORS -p POLY
                           [-e EXCLUDE] [-o OUT]

optional arguments:
  -h, --help            show this help message and exit
  -r REF, --ref REF     Contig level assembly fasta
  -b BAM, --bam BAM     Prunned bam file
  -d BED, --bed BED     dup.bed
  -a ANCHORS, --anchors ANCHORS
                        anchors file with dup.mono.anchors
  -p POLY, --poly POLY  Ploid count of polyploid
  -e EXCLUDE, --exclude EXCLUDE
                        A list file contains exclude contigs for partition,
                        default=""
  -o OUT, --out OUT     Output directory, default=workdir
```

**ALLHiC_rescue.py** is a new version of rescue use jcvi to prevent the collinear contigs be rescued to same group.
```bash
usage: ALLHiC_rescue.py [-h] -r REF -b BAM -c CLUSTER -n COUNTS -g GFF3 -j
                        JCVI [-e EXCLUDE] [-w WORKDIR]

optional arguments:
  -h, --help            show this help message and exit
  -r REF, --ref REF     Contig level assembly fasta
  -b BAM, --bam BAM     Unprunned bam
  -c CLUSTER, --cluster CLUSTER
                        Cluster file of contigs
  -n COUNTS, --counts COUNTS
                        count REs file
  -g GFF3, --gff3 GFF3  Gff3 file generated by gmap cds to contigs
  -j JCVI, --jcvi JCVI  CDS file for jcvi, bed file with same prefix must
                        exist in the same position
  -e EXCLUDE, --exclude EXCLUDE
                        cluster which need no rescue, default="", split by
                        comma
  -w WORKDIR, --workdir WORKDIR
                        Work directory, default=wrkdir
```

**ALLHiC_plot.py** is used to plot heatmap of Hi-C singal, and compare with original version, it can reduce the usage of memory, and easier plot heatmap with other resolution.
```bash
# Notice: bam file must be indexed
usage: ALLHiC_plot.py [-h] -b BAM -l LIST [-a AGP] [-5 H5] [-m MIN_SIZE] [-s SIZE] [-c CMAP] [-o OUTDIR] [--line | --block] [--linecolor LINECOLOR] [-t THREAD]

options:
  -h, --help            show this help message and exit
  -b BAM, --bam BAM     Input bam file
  -l LIST, --list LIST  Chromosome list, contain: ID Length
  -a AGP, --agp AGP     Input AGP file, if bam file is a contig-level mapping, agp file is required
  -5 H5, --h5 H5        h5 file of hic signal, optional, if not exist, it will be generate after reading hic signals, or it will be loaded for drawing other resolution of heatmap
  -m MIN_SIZE, --min_size MIN_SIZE
                        Minium bin size of heatmap, default=50k
  -s SIZE, --size SIZE  Bin size of heatmap, can be a list separated by comma, default=500k, notice: it must be n times of min_size (n is integer) or we will adjust it to nearest one
  -c CMAP, --cmap CMAP  CMAP for drawing heatmap, default="YlOrRd"
  -o OUTDIR, --outdir OUTDIR
                        Output directory, default=workdir
  --line                Draw dash line for each chromosome
  --block               Draw dash block for each chromosome
  --linecolor LINECOLOR
                        Color of dash line or dash block, default="grey"
  -t THREAD, --thread THREAD
                        Threads for reading bam, default=1
```

**Other scripts** are under development, and not recommend to use.
