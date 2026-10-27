/-!
# SHA-256

The events of a challenge form a hash chain, and a challenge's id is the start of its opening event's hash, so
the core computes SHA-256 itself (FIPS 180-4). Checked against the standard test vectors in `Tests.lean`.
-/

namespace Challenge.Sha256

def roundConstants : Array UInt32 := #[
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2]

def initialHash : Array UInt32 :=
  #[0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]

@[inline] def rotr (x n : UInt32) : UInt32 := (x >>> n) ||| (x <<< (32 - n))

/-- The message, a 1 bit, zeros, and the message length in bits, to a multiple of 64 bytes. -/
def pad (msg : ByteArray) : ByteArray := Id.run do
  let bits := msg.size * 8
  let zeros := (64 + 55 - msg.size % 64) % 64
  let mut out := msg.push 0x80
  for _ in [0:zeros] do
    out := out.push 0
  for i in [0:8] do
    out := out.push (UInt8.ofNat ((bits >>> (8 * (7 - i))) % 256))
  return out

def byteAt (b : ByteArray) (i : Nat) : UInt32 := (b.get! i).toUInt32

/-- One 64-byte block, starting at `off`. -/
def compress (st : Array UInt32) (blk : ByteArray) (off : Nat) : Array UInt32 := Id.run do
  let mut w : Array UInt32 := #[]
  for i in [0:16] do
    let j := off + 4 * i
    w := w.push ((byteAt blk j <<< 24) ||| (byteAt blk (j + 1) <<< 16) ||| (byteAt blk (j + 2) <<< 8) |||
      byteAt blk (j + 3))
  for i in [16:64] do
    let w15 := w[i - 15]!
    let w2 := w[i - 2]!
    let s0 := rotr w15 7 ^^^ rotr w15 18 ^^^ (w15 >>> 3)
    let s1 := rotr w2 17 ^^^ rotr w2 19 ^^^ (w2 >>> 10)
    w := w.push (w[i - 16]! + s0 + w[i - 7]! + s1)
  let mut a := st[0]!
  let mut b := st[1]!
  let mut c := st[2]!
  let mut d := st[3]!
  let mut e := st[4]!
  let mut f := st[5]!
  let mut g := st[6]!
  let mut h := st[7]!
  for i in [0:64] do
    let bigS1 := rotr e 6 ^^^ rotr e 11 ^^^ rotr e 25
    let ch := (e &&& f) ^^^ ((~~~e) &&& g)
    let t1 := h + bigS1 + ch + roundConstants[i]! + w[i]!
    let bigS0 := rotr a 2 ^^^ rotr a 13 ^^^ rotr a 22
    let maj := (a &&& b) ^^^ (a &&& c) ^^^ (b &&& c)
    let t2 := bigS0 + maj
    h := g
    g := f
    f := e
    e := d + t1
    d := c
    c := b
    b := a
    a := t1 + t2
  return #[st[0]! + a, st[1]! + b, st[2]! + c, st[3]! + d, st[4]! + e, st[5]! + f, st[6]! + g, st[7]! + h]

def hexDigit (n : Nat) : Char := if n < 10 then Char.ofNat (48 + n) else Char.ofNat (87 + n)

def hex32 (x : UInt32) : String := Id.run do
  let mut s := ""
  for i in [0:8] do
    s := s.push (hexDigit ((x >>> UInt32.ofNat (28 - 4 * i)) &&& 0xf).toNat)
  return s

/-- The SHA-256 of some bytes, as 64 lowercase hex digits. -/
def hash (msg : ByteArray) : String :=
  let p := pad msg
  let st := Id.run do
    let mut st := initialHash
    for i in [0:p.size / 64] do
      st := compress st p (64 * i)
    return st
  String.join (st.toList.map hex32)

end Challenge.Sha256

namespace Challenge

/-- The SHA-256 of a string's UTF-8 bytes, which is how an event file's hash is taken. -/
def hashString (s : String) : String := Sha256.hash s.toUTF8

end Challenge
