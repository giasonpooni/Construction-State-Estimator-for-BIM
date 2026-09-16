//! Live effort authority on the far side of the Rust ingest gate.
//! Policy only. Does not invoke CUDA or SP1. Does not touch Beam-B1.

use serde_json::{json, Value};
use std::env;
use std::fs;
use std::process;

const FORMAT: &str = "satellite-effort-v1";
const AUTHORITY: &str = "rust-effort-gate";

fn main() {
    match run(env::args().skip(1).collect()) {
        Ok(value) => {
            println!("{}", value);
        }
        Err(err) => {
            eprintln!("{err}");
            process::exit(1);
        }
    }
}

fn run(args: Vec<String>) -> Result<Value, String> {
    let mut table_path = String::from("validation/satellite-effort-v1.json");
    let mut satellite = String::new();
    let mut hole: Option<String> = None;
    let mut information: Option<f64> = None;
    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--table" => {
                table_path = next(&args, &mut i)?.to_string();
            }
            "--satellite" => {
                satellite = next(&args, &mut i)?.to_string();
            }
            "--hole" => {
                hole = Some(next(&args, &mut i)?.to_string());
            }
            "--information-nats" => {
                let raw = next(&args, &mut i)?;
                information = Some(
                    raw.parse::<f64>()
                        .map_err(|_| format!("information-nats must be a number: {raw}"))?,
                );
            }
            other => return Err(format!("unknown argument {other}")),
        }
        i += 1;
    }
    if satellite.is_empty() {
        return Err("--satellite is required".into());
    }
    let table: Value = serde_json::from_str(
        &fs::read_to_string(&table_path).map_err(|err| format!("{table_path}: {err}"))?,
    )
    .map_err(|err| format!("{table_path}: {err}"))?;
    if table.get("format").and_then(Value::as_str) != Some(FORMAT) {
        return Err("effort table format must be satellite-effort-v1".into());
    }
    Ok(decide(&table, &satellite, hole.as_deref(), information))
}

fn next<'a>(args: &'a [String], i: &mut usize) -> Result<&'a str, String> {
    *i += 1;
    args.get(*i)
        .map(String::as_str)
        .ok_or_else(|| "missing argument value".into())
}

fn decide(table: &Value, name: &str, hole: Option<&str>, information: Option<f64>) -> Value {
    let mut disposition = "REFUSE";
    let mut reason = "unknown satellite";
    let mut allowed = false;
    let mut cost: Option<f64> = None;
    let entry = table
        .get("satellites")
        .and_then(Value::as_object)
        .and_then(|s| s.get(name));
    if let Some(entry) = entry {
        allowed = entry.get("allowed").and_then(Value::as_bool).unwrap_or(false);
        cost = entry.get("cost_nats").and_then(Value::as_f64);
        let authority = entry
            .get("authority")
            .and_then(Value::as_str)
            .unwrap_or("python");
        if authority != AUTHORITY {
            disposition = "REFUSE";
            reason = "this binary is not the authority for that satellite";
        } else if cost.map(|c| c.is_finite() && c >= 0.0) != Some(true) {
            disposition = "REFUSE";
            reason = "cost_nats missing or not finite";
            cost = None;
        } else if !allowed {
            disposition = "REFUSE";
            reason = "allowed is false";
        } else if hole.map(|h| !h.is_empty()) != Some(true)
            || information.map(|v| v.is_finite() && v >= 0.0) != Some(true)
        {
            disposition = "DEFER";
            reason = "need a named hole and finite expected information";
        } else if information.unwrap() - cost.unwrap() <= 0.0 {
            disposition = "DEFER";
            reason = "I - c <= 0";
        } else {
            disposition = "INVOKE";
            reason = "declared information exceeds declared cost";
        }
    }
    json!({
        "type": "policy",
        "satellite": name,
        "disposition": disposition,
        "cost_nats": cost,
        "expected_information_nats": information,
        "hole": hole,
        "reason": reason,
        "allowed": allowed,
        "authority": AUTHORITY,
        "world_digest_unchanged": true,
        "invoked": false
    })
}
