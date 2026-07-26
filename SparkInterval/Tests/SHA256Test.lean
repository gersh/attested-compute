import SparkInterval.Certificate.SHA256

/-! Known-answer tests for the pure Phase 8 SHA-256 implementation. -/

set_option autoImplicit false

namespace SparkInterval.Tests.SHA256

open SparkInterval.Certificate

#guard SHA256.digestString "" =
  "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

#guard SHA256.digestString "abc" =
  "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"

#guard SHA256.digestString (String.ofList (List.replicate 55 'a')) =
  "9f4390f8d30c2dd92ec9f095b65e2b9ae9b0a925a5258e241c9f1e910f734318"

#guard SHA256.digestString (String.ofList (List.replicate 56 'a')) =
  "b35439a4ac6f0948b6d6f9e3c6af0f5f590ce20f1bde7090ef7970686ec6738a"

#guard SHA256.digestString (String.ofList (List.replicate 57 'a')) =
  "f13b2d724659eb3bf47f2dd6af1accc87b81f09f59f2b75e5c0bed6589dfe8c6"

#guard SHA256.digestString (String.ofList (List.replicate 63 'a')) =
  "7d3e74a05d7db15bce4ad9ec0658ea98e3f06eeecf16b4c6fff2da457ddc2f34"

#guard SHA256.digestString (String.ofList (List.replicate 64 'a')) =
  "ffe054fe7ae0cb6dc65c3af9b61d5209f439851db43d0ba5997337df154668eb"

#guard SHA256.digestString (String.ofList (List.replicate 65 'a')) =
  "635361c48bb9eab14198e76ea8ab7f1a41685d6ad62aa9146d301d4f17eb0ae0"

#guard SHA256.digestString (String.ofList (List.replicate 1000 'a')) =
  "41edece42d63e8d9bf515a9ba6932e1c20cbc9f5a5d134645adb5db1b9737ea3"

#guard SHA256.digestString "ζ certificate" =
  "db43a9a2858b0b55b49dbf03595fdef73876c4a4017e2d8063fdf820bf4ad640"

end SparkInterval.Tests.SHA256
