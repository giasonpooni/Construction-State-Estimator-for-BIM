#![no_main]

use gat_sp1_kernel_lib::{chain_jvp_i32, ChainInput};

sp1_zkvm::entrypoint!(main);

pub fn main() {
    let input: ChainInput = sp1_zkvm::io::read();
    let y = chain_jvp_i32(&input).expect("i32 chain-JVP overflow");
    sp1_zkvm::io::commit(&y);
}
