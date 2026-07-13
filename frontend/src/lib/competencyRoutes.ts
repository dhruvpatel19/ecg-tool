type IndependentReceipt = {
  mode: "train" | "rapid";
  caseConcept: string;
  receiptConcept: string;
  subskill: string;
};

export function competencyPracticeHref(receipt: IndependentReceipt | null): string | null {
  if (!receipt) return null;
  const params = new URLSearchParams({
    receiptConcept: receipt.receiptConcept,
    subskill: receipt.subskill,
    returnTo: "/profile",
  });
  if (receipt.mode === "train") {
    params.set("concept", receipt.caseConcept);
    return `/train?${params.toString()}`;
  }
  params.set("focus", receipt.caseConcept);
  return `/rapid?${params.toString()}`;
}
