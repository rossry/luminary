TARGET_EXEC ?= a.out

BIN_DIR ?= ./bin
BUILD_DIR ?= ./build
SRC_DIRS ?= ./src ./lib

SRCS := $(shell find $(SRC_DIRS) -name *.cpp -or -name *.c -or -name *.s)
OBJS := $(SRCS:%=$(BUILD_DIR)/%.o)
DEPS := $(OBJS:.o=.d)

INC_DIRS := $(shell find $(SRC_DIRS) -type d)
INC_FLAGS := $(addprefix -I,$(INC_DIRS)) -I/usr/include/cairo

CFLAGS ?= -Wall -Ofast -std=c99 -D _BSD_SOURCE -Wno-unused-result
CPPFLAGS ?= $(INC_FLAGS) -MMD -MP
CXXFLAGS ?=  -Wall -Ofast -std=c++11

PP_LIBDIR=lib/pp-server/lib
PP_LIBRARY_NAME=pixel-push-server
PP_LIBRARY=$(PP_LIBDIR)/lib$(PP_LIBRARY_NAME).a

#LDFLAGS=-lncurses -L$(PP_LIBDIR) -l$(PP_LIBRARY_NAME) -lstdc++ -lrt -lm -lpthread -lcairo -lX11
LDFLAGS=-lncurses -lstdc++ -lrt -lm -lpthread -lcairo -lX11
#LDFLAGS=-lncurses -lstdc++ -lrt -lm -lpthread

$(BIN_DIR)/$(TARGET_EXEC): $(OBJS)
	#$(PP_LIBRARY)
	$(CC) $(OBJS) -o $@ $(LDFLAGS)

# pp-server
#$(PP_LIBRARY): FORCE
#	$(MAKE) -C $(PP_LIBDIR)

# assembly
$(BUILD_DIR)/%.s.o: %.s
	$(MKDIR_P) $(dir $@)
	$(AS) $(ASFLAGS) -c $< -o $@

# c source
$(BUILD_DIR)/%.c.o: %.c
	$(MKDIR_P) $(dir $@)
	$(CC) $(CPPFLAGS) $(CFLAGS) -c $< -o $@

# c++ source
$(BUILD_DIR)/%.cpp.o: %.cpp
	$(MKDIR_P) $(dir $@)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c $< -o $@


.PHONY: clean

clean:
	$(RM) -r $(BUILD_DIR)

-include $(DEPS)

MKDIR_P ?= mkdir -p

FORCE:
.PHONY: FORCE