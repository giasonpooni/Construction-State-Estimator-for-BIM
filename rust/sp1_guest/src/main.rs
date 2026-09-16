//! Guest-shaped entry. Runs the i32 kernels on the host.
//! This is the program a later SP1 guest would execute.
//! It does not call the Succinct prover. invoked stays false.

use cse_fixedpoint_kernel::{chain_jvp_i32, discrete_lyapunov_decrease_i32, Mat2, Vec2};
use std::env;
use std::process;

fn main() {
    let kernel = env::args().nth(1).unwrap_or_else(|| "chain_jvp".into());
    match kernel.as_str() {
        "chain_jvp" => match chain_jvp_i32(
            Mat2([[2, 0], [0, 3]]),
            Vec2([1, 1]),
            Mat2([[1, 1], [0, 1]]),
        ) {
            Ok(y) => {
                println!("{{\"kernel\":\"chain_jvp_i32\",\"y\":[{},{}],\"invoked\":false}}", y.0[0], y.0[1]);
            }
            Err(err) => {
                eprintln!("{err}");
                process::exit(1);
            }
        },
        "lyapunov" => match discrete_lyapunov_decrease_i32(
            Mat2([[0, 1], [0, 0]]),
            Mat2([[1, 0], [0, 1]]),
            Vec2([2, 1]),
        ) {
            Ok(report) => {
                println!(
                    "{{\"kernel\":\"discrete_lyapunov_decrease_i32\",\"V\":{},\"V_next\":{},\"decreases\":{},\"invoked\":false}}",
                    report.v, report.v_next, report.decreases
                );
            }
            Err(err) => {
                eprintln!("{err}");
                process::exit(1);
            }
        },
        other => {
            eprintln!("unknown kernel {other}; expected chain_jvp or lyapunov");
            process::exit(2);
        }
    }
}
