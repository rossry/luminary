#!/bin/bash

# run this from luminary root
make
bin/a.out
ffmpeg -r 50 -i demo/v2-1a/img0000%04d.png -c:v libx264 -vf fps=50 -pix_fmt yuv420p demo/n2-1a_50hz.mp4
