//! i32 discrete maps. No float. Same pin as validation/sp1-kernel-i32-v0.json.

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Mat2(pub [[i32; 2]; 2]);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Vec2(pub [i32; 2]);

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

/// y = J2 (J1 dx)
pub fn chain_jvp_i32(j1: Mat2, dx: Vec2, j2: Mat2) -> Result<Vec2, &'static str> {
    mv(j2, mv(j1, dx)?)
}

pub fn quadratic_i32(p: Mat2, x: Vec2) -> Result<i32, &'static str> {
    let px = mv(p, x)?;
    dot(x.0, px)
}

#[derive(Debug, PartialEq, Eq)]
pub struct LyapunovSample {
    pub x_next: Vec2,
    pub v: i32,
    pub v_next: i32,
    pub decreases: bool,
}

pub fn discrete_lyapunov_decrease_i32(
    a: Mat2,
    p: Mat2,
    x: Vec2,
) -> Result<LyapunovSample, &'static str> {
    let x_next = mv(a, x)?;
    let v = quadratic_i32(p, x)?;
    let v_next = quadratic_i32(p, x_next)?;
    Ok(LyapunovSample {
        x_next,
        v,
        v_next,
        decreases: v_next < v,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn chain_jvp_pin() {
        let y = chain_jvp_i32(
            Mat2([[2, 0], [0, 3]]),
            Vec2([1, 1]),
            Mat2([[1, 1], [0, 1]]),
        )
        .unwrap();
        assert_eq!(y, Vec2([5, 3]));
    }

    #[test]
    fn lyapunov_pin() {
        let report = discrete_lyapunov_decrease_i32(
            Mat2([[0, 1], [0, 0]]),
            Mat2([[1, 0], [0, 1]]),
            Vec2([2, 1]),
        )
        .unwrap();
        assert_eq!(report.v, 5);
        assert_eq!(report.v_next, 1);
        assert_eq!(report.x_next, Vec2([1, 0]));
        assert!(report.decreases);
    }
}
