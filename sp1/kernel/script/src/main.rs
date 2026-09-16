use std::path::PathBuf;

use anyhow::{bail, Context, Result};
use clap::{Parser, Subcommand};
use gat_sp1_kernel_lib::{chain_jvp_i32, pin_input, pin_output};
use sp1_sdk::{
    blocking::{Prover, ProverClient},
    include_elf, Elf, SP1Stdin,
};

const ELF: Elf = include_elf!("gat-sp1-kernel-program");

#[derive(Debug, Parser)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    Execute,
    Prove {
        #[arg(long)]
        proof: PathBuf,
    },
}

fn main() -> Result<()> {
    match Cli::parse().command {
        Command::Execute => execute(),
        Command::Prove { proof } => prove(&proof),
    }
}

fn stdin_pin() -> Result<SP1Stdin> {
    let input = pin_input();
    if chain_jvp_i32(&input).context("host pin failed")? != pin_output() {
        bail!("host pin does not match declared y=[5,3]");
    }
    let mut stdin = SP1Stdin::new();
    stdin.write(&input);
    Ok(stdin)
}

fn execute() -> Result<()> {
    let client = ProverClient::from_env();
    let (public_values, report) = client
        .execute(ELF, stdin_pin()?)
        .run()
        .context("SP1 kernel execute failed")?;
    let y = public_values
        .read::<gat_sp1_kernel_lib::Vec2>()
        .context("could not read committed y")?;
    if y != pin_output() {
        bail!("guest y {:?} != pin [5,3]", y);
    }
    println!(
        "SP1 kernel execute passed ({} cycles) y=[5,3]",
        report.total_instruction_count()
    );
    Ok(())
}

fn prove(proof_path: &PathBuf) -> Result<()> {
    let client = ProverClient::from_env();
    let pk = client.setup(ELF).context("SP1 setup failed")?;
    let proof = client
        .prove(&pk, stdin_pin()?)
        .run()
        .context("SP1 kernel prove failed")?;
    let y = proof
        .public_values
        .read::<gat_sp1_kernel_lib::Vec2>()
        .context("could not read committed y")?;
    if y != pin_output() {
        bail!("proved y {:?} != pin [5,3]", y);
    }
    client
        .verify(&proof, pk.verifying_key(), None)
        .context("SP1 kernel verify failed")?;
    proof.save(proof_path).context("could not save proof")?;
    println!("SP1 kernel proof verified and saved to {}", proof_path.display());
    Ok(())
}
