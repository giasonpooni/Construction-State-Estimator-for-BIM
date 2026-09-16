//! i32 chain-rule JVP. Same pin as validation/sp1-kernel-i32-v0.json.
use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct Mat2(pub [[i32; 2]; 2]);

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct Vec2(pub [i32; 2]);

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct ChainInput {
    pub j1: Mat2,
    pub dx: Vec2,
    pub j2: Mat2,
}

fn mul(a: i32, b: i32) -> Result<i32, &'static str> {
    a.checked_mul(b).ok_or("i32 multiply overflow")
}

fn add(a: i32, b: i32) -> Result<i32, &'static str> {
    a.checked_add(b).ok_or("i32 add overflow")
}

fn dot(row: [i32; 2], v: Vec2) -> Result<i32, &'static str> {
    add(mul(row[0], v.0[0])?, mul(row[1], v.0[1])?)
}

pub fn mv(m: Mat2, v: Vec2) -> Result<Vec2, &'static str> {
    Ok(Vec2([dot(m.0[0], v)?, dot(m.0[1], v)?]))
}

pub fn chain_jvp_i32(input: &ChainInput) -> Result<Vec2, &'static str> {
    mv(input.j2, mv(input.j1, input.dx)?)
}

pub fn pin_input() -> ChainInput {
    ChainInput {
        j1: Mat2([[2, 0], [0, 3]]),
        dx: Vec2([1, 1]),
        j2: Mat2([[1, 1], [0, 1]]),
    }
}

pub fn pin_output() -> Vec2 {
    Vec2([5, 3])
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pin() {
        assert_eq!(chain_jvp_i32(&pin_input()).unwrap(), pin_output());
    }
}
