# Host conformance test for the C++ decoder core (spec §17.2.5).
#   make && ./test_decoder ../../golden/case1

CXX ?= g++
CXXFLAGS ?= -std=c++17 -O2 -Wall -Wextra
LUMICODEC = ../../scorpio/lib/lumicodec

test_decoder: test_decoder.cpp $(LUMICODEC)/lumicodec.cpp $(LUMICODEC)/lumicodec.h
	$(CXX) $(CXXFLAGS) -I$(LUMICODEC) test_decoder.cpp $(LUMICODEC)/lumicodec.cpp -o $@

.PHONY: clean run
run: test_decoder
	./test_decoder ../../golden/case1

clean:
	rm -f test_decoder
