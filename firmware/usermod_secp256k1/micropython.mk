# โมดูล C: สะพานไป libsecp256k1 — ใช้กับพอร์ต unix (make) เพื่อเทสบนแมค
SECP256K1_MOD_DIR := $(USERMOD_DIR)
SECP256K1_DIR ?= $(HOME)/picobuild/secp256k1

SRC_USERMOD_C += $(SECP256K1_MOD_DIR)/secp256k1mod.c $(SECP256K1_MOD_DIR)/libsecp256k1_unity.c
CFLAGS_USERMOD += -I$(SECP256K1_MOD_DIR) -I$(SECP256K1_DIR)/include -I$(SECP256K1_DIR)/src \
                  -DECMULT_WINDOW_SIZE=4 -DCOMB_BLOCKS=11 -DCOMB_TEETH=6
