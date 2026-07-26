import SparkInterval.Dirichlet.FactoredSmallQSeed

set_option autoImplicit false

namespace SparkInterval.Tests.FactoredSmallQSeed

open SparkInterval.Certified
open SparkInterval.Dirichlet.FactoredSmallQSeed

example {certificate : PrefactorCertificate} {base epsilon : ℂ}
    (hbase : certificate.parityBase.ContainsComplex base)
    (hepsilon : certificate.epsilon.ContainsComplex epsilon) :
    certificate.expand.ContainsComplex (base * epsilon) :=
  PrefactorCertificate.expand_contains hbase hepsilon

example {W : ComplexRect} {w : ℂ} (hw : W.ContainsComplex w) (n : ℕ) :
    (RectGaussianState.after W n).z.ContainsComplex (w ^ ((n + 1) ^ 2)) :=
  (RectGaussianState.after_contains_powers hw n).1

example {certificate : DiskPrefactorCertificate} {base epsilon : ℂ}
    (hcheck : certificate.check = true)
    (hbase : certificate.parityBase.ContainsComplex base)
    (hepsilon : certificate.epsilon.ContainsComplex epsilon) :
    certificate.expanded.ContainsComplex (base * epsilon) :=
  DiskPrefactorCertificate.expanded_contains hcheck hbase hepsilon

#print axioms PrefactorCertificate.expand_contains
#print axioms DiskPrefactorCertificate.expanded_contains
#print axioms RectGaussianState.after_contains_powers

end SparkInterval.Tests.FactoredSmallQSeed
