const TERMS: {term: string; meaning: string}[] = [
  {term: 'Model score', meaning: 'A detector output after its documented sigmoid or softmax transformation. Uncalibrated; not a probability that the file is manipulated.'},
  {term: 'Decision threshold', meaning: 'A development rule used to surface evidence. It is not a DPS-validated operational threshold unless explicitly marked validated.'},
  {term: 'Estimated probability', meaning: 'Shown only after a calibration procedure is fitted and versioned for the checkpoint.'},
  {term: 'Attribution', meaning: 'Regions or spans that influenced the model output. This shows model sensitivity, not proof of manipulation.'},
];

export function Terms() {
  return <details className="terms">
    <summary>Terms</summary>
    <dl>{TERMS.map(item => <div key={item.term}><dt>{item.term}</dt><dd>{item.meaning}</dd></div>)}</dl>
  </details>;
}
