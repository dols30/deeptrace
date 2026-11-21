import {formatBytes, type ComponentResult, type Report} from './api';
import {assessment, coverageDescription, label, observation, outcome, score, time} from './report-presentation';
import {HELVETICA, HELVETICA_BOLD} from './pdf-font-metrics';

type Font = 'F1' | 'F2' | 'F3';
type Color = [number, number, number];
type Style = {size?: number; font?: Font; color?: Color; leading?: number};
type Page = {commands: string[]; y: number; section: string};
type Cell = {text: string; font?: Font; color?: Color};
const WIDTH = 612, HEIGHT = 792, LEFT = 54, RIGHT = 558, BODY = RIGHT - LEFT, BOTTOM = 728;
const INK: Color = [.12, .15, .19], MUTED: Color = [.27, .31, .36], LINE: Color = [.83, .85, .88], PALE: Color = [.96, .97, .98];
const WIN_ANSI: Record<string, number> = {'€':128,'‚':130,'ƒ':131,'„':132,'…':133,'†':134,'‡':135,'ˆ':136,'‰':137,'Š':138,'‹':139,'Œ':140,'Ž':142,'‘':145,'’':146,'“':147,'”':148,'•':149,'–':150,'—':151,'˜':152,'™':153,'š':154,'›':155,'œ':156,'ž':158,'Ÿ':159};

function printable(value: unknown): string {
  return String(value ?? '').normalize('NFC').replace(/\r\n?/g, '\n').replace(/\t/g, ' ')
    .replace(/[\u2010-\u2015]/g, '-').replace(/[\u2018\u2019]/g, "'").replace(/[\u201c\u201d]/g, '"')
    .replace(/\u00a0/g, ' ').replace(/[\u0000-\u0008\u000b-\u001f\u007f]/g, '')
    .split('').map(char => {
      const code = char.charCodeAt(0);
      if (code < 256 || WIN_ANSI[char]) return char;
      // Keep unrepresentable characters explicit instead of silently dropping them.
      return '[U+' + code.toString(16).toUpperCase().padStart(4, '0') + ']';
    }).join('');
}
function charCode(char: string): number { return WIN_ANSI[char] ?? char.charCodeAt(0); }
function pdfString(value: string): string {
  return printable(value).split('').map(char => {
    const code = charCode(char);
    return code > 126 ? '\\' + code.toString(8).padStart(3, '0') : /[\\()]/.test(char) ? '\\' + char : char;
  }).join('');
}
function width(value: string, size: number, font: Font): number {
  const metrics = font === 'F2' ? HELVETICA_BOLD : HELVETICA;
  return [...printable(value)].reduce((sum, char) => sum + (font === 'F3' ? 600 : metrics[charCode(char) - 32] ?? 556), 0) * size / 1000;
}
function lines(value: string, maxWidth: number, size: number, font: Font): string[] {
  const result: string[] = [];
  for (const paragraph of printable(value).split('\n')) {
    let current = '';
    for (const word of paragraph.trim().split(/\s+/).filter(Boolean)) {
      if (current && width(current + ' ' + word, size, font) <= maxWidth) { current += ' ' + word; continue; }
      if (current) { result.push(current); current = ''; }
      let part = '';
      for (const char of word) {
        if (part && width(part + char, size, font) > maxWidth) { result.push(part); part = ''; }
        part += char;
      }
      current = part;
    }
    result.push(current);
  }
  return result;
}
function n(value: number): string { return Number(value.toFixed(3)).toString(); }
function number(value: number | null | undefined, digits = 3): string {
  return value == null || !Number.isFinite(value) ? 'Not available' : value.toFixed(digits);
}
function date(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? value : parsed.toISOString().replace('T', ' ').replace(/\.\d+Z$/, ' UTC');
}
function human(value: string): string { return value.replaceAll('_', ' ').replace(/^./, char => char.toUpperCase()); }
function coverage(component: ComponentResult, report: Report): string {
  if (component.status === 'not_applicable') return 'Not applicable';
  if (component.coverage) return coverageDescription(component);
  if (component.status !== 'functional') return 'Not completed';
  if (component.component === 'audio' && /aasist/i.test(component.model_name)) {
    return 'Opening ' + Math.min(report.media.duration_seconds ?? 4.0375, 4.0375).toFixed(2) + ' seconds';
  }
  if (component.num_samples != null) return component.num_samples + ' samples reported';
  return component.component === 'audio' ? 'File-level output' : 'Sample count not reported';
}

class ReportDocument {
  pages: Page[] = [];
  page!: Page;
  section = 'Screening overview';
  constructor(private report: Report) { this.newPage(true); }

  draw(value: string, x: number, top: number, style: Style = {}) {
    const size = style.size ?? 10, font = style.font ?? 'F1', color = style.color ?? INK;
    this.page.commands.push('BT /' + font + ' ' + n(size) + ' Tf ' + color.join(' ') + ' rg 1 0 0 1 ' + n(x) + ' ' + n(HEIGHT - top - size) + ' Tm (' + pdfString(value) + ') Tj ET');
  }
  rule(top: number, x = LEFT, length = BODY, color = LINE) {
    this.page.commands.push(color.join(' ') + ' RG 0.5 w ' + n(x) + ' ' + n(HEIGHT - top) + ' m ' + n(x + length) + ' ' + n(HEIGHT - top) + ' l S');
  }
  fill(top: number, height: number, color = PALE, x = LEFT, length = BODY) {
    this.page.commands.push(color.join(' ') + ' rg ' + n(x) + ' ' + n(HEIGHT - top - height) + ' ' + n(length) + ' ' + n(height) + ' re f');
  }
  newPage(first = false) {
    this.page = {commands: [], y: first ? 144 : 78, section: this.section};
    this.pages.push(this.page);
    if (first) {
      this.draw('DEEPTRACE', LEFT, 40, {size:11, font:'F2'});
      this.draw('ADVISORY SCREENING', RIGHT - width('ADVISORY SCREENING', 8, 'F1'), 42, {size:8, color:MUTED});
      this.draw('Media screening report', LEFT, 61, {size:23, font:'F2'});
      this.draw('Report ID', LEFT, 100, {size:9.5, color:MUTED});
      this.draw(this.report.report_id, LEFT + 58, 100, {size:9.5, font:'F3'});
      this.draw('Generated', LEFT, 116, {size:9.5, color:MUTED});
      this.draw(date(this.report.generated_at), LEFT + 58, 116, {size:9.5});
      this.rule(138);
    } else {
      this.draw('DEEPTRACE / MEDIA SCREENING', LEFT, 34, {size:8, font:'F2', color:MUTED});
      const ref = this.report.report_id.slice(0, 8) + ' / ' + this.section;
      this.draw(ref, RIGHT - width(ref, 8, 'F1'), 34, {size:8, color:MUTED});
      this.rule(57);
    }
  }
  ensure(height: number): boolean {
    if (this.page.y + height <= BOTTOM) return false;
    this.newPage();
    return true;
  }
  space(height = 8) { this.page.y += height; }
  paragraph(value: string, style: Style = {}, indent = 0, maxWidth = BODY - indent) {
    const size = style.size ?? 10, font = style.font ?? 'F1', leading = style.leading ?? size * 1.42;
    for (const line of lines(value, maxWidth, size, font)) {
      this.ensure(leading);
      this.draw(line, LEFT + indent, this.page.y, style);
      this.page.y += leading;
    }
    this.space(5);
  }
  heading(value: string, major = true) {
    this.section = value;
    const size = major ? 12.5 : 11;
    this.ensure(size + 44);
    this.space(major ? 8 : 7);
    this.draw(value, LEFT, this.page.y, {size, font:'F2'});
    this.page.y += size + 8;
  }
  appendix(title: string) {
    this.section = title;
    this.newPage();
    this.paragraph(title, {size:18, font:'F2', leading:24});
    this.space(8);
  }
  field(labelText: string, value: unknown, mono = false) {
    this.table([], [[{text:labelText, color:MUTED}, {text:value == null || value === '' ? 'Not reported' : String(value), font:mono ? 'F3' : 'F1'}]], [112, BODY - 112], false, 10, 5);
  }
  facts(items: [string, string][], columns = 3) {
    const gutter = 18, cellWidth = (BODY - gutter * (columns - 1)) / columns;
    for (let i = 0; i < items.length; i += columns) {
      const row = items.slice(i, i + columns);
      const labels = row.map(([key]) => lines(key, cellWidth, 9.3, 'F1'));
      const labelHeight = Math.max(...labels.map(item => item.length)) * 12 + 3;
      const wrapped = row.map(([,value]) => lines(value, cellWidth, 10, 'F1'));
      const height = labelHeight + Math.max(...wrapped.map(item => item.length)) * 14 + 10;
      if (height > BOTTOM - 78) { row.forEach(([key,value]) => this.field(key,value)); continue; }
      this.ensure(height);
      const top = this.page.y;
      row.forEach(([key], index) => {
        const x = LEFT + index * (cellWidth + gutter);
        labels[index].forEach((line,lineIndex) => this.draw(line,x,top+lineIndex*12,{size:9.3,color:MUTED}));
        wrapped[index].forEach((line,lineIndex) => this.draw(line, x, top + labelHeight + lineIndex * 14, {size:10}));
      });
      this.page.y += height;
    }
  }
  table(headers: string[], rows: (string | Cell)[][], widths: number[], ruled = true, size = 9, padding = 7) {
    const leading = size * 1.38;
    const headerHeight = headers.length ? 26 : 0;
    const header = () => {
      if (!headers.length) return;
      this.fill(this.page.y, headerHeight);
      let x = LEFT;
      headers.forEach((value,index) => {
        this.draw(value, x + padding, this.page.y + 7, {size:9, font:'F2', color:MUTED});
        x += widths[index];
      });
      this.page.y += headerHeight;
    };
    if (rows.length) this.ensure(headerHeight + Math.min(44, padding * 2 + leading * 2));
    header();
    for (const row of rows) {
      const cells = row.map(value => typeof value === 'string' ? {text:value} : value);
      const wrapped = cells.map((cell,index) => lines(cell.text, widths[index] - padding * 2, size, cell.font ?? 'F1'));
      let offset = 0;
      const rowLines = Math.max(1, ...wrapped.map(item => item.length));
      while (offset < rowLines) {
        let capacity = Math.floor((BOTTOM - this.page.y - padding * 2) / leading);
        if (capacity < 1) { this.newPage(); header(); capacity = Math.floor((BOTTOM - this.page.y - padding * 2) / leading); }
        const count = Math.min(rowLines - offset, capacity);
        const height = Math.max(ruled ? (size < 10 ? 22 : 30) : 0, count * leading + padding * 2);
        if (this.page.y + height > BOTTOM) { this.newPage(); header(); continue; }
        const top = this.page.y;
        let x = LEFT;
        cells.forEach((cell,index) => {
          const chunk = wrapped[index].slice(offset, offset + count);
          chunk.forEach((line,lineIndex) => this.draw(line, x + padding, top + padding + lineIndex * leading, {size, font:cell.font, color:cell.color}));
          x += widths[index];
        });
        this.page.y += height;
        if (ruled) this.rule(this.page.y);
        offset += count;
        if (offset < rowLines) { this.newPage(); header(); }
      }
    }
  }
  bullets(items: string[]) {
    for (const item of items) {
      const wrapped = lines(item, BODY - 13, 10, 'F1');
      this.ensure(27);
      wrapped.forEach((line,index) => {
        this.ensure(14.4);
        if (index === 0) this.draw('-', LEFT, this.page.y, {size:10});
        this.draw(line, LEFT + 13, this.page.y, {size:10});
        this.page.y += 14.4;
      });
      this.space(6);
    }
  }
  blob(): Blob {
    this.pages.forEach((page,index) => {
      this.page = page;
      this.rule(749);
      this.draw('Advisory screening - qualified human review required', LEFT, 760, {size:8.5, color:MUTED});
      const pageNumber = String(index + 1) + ' / ' + this.pages.length;
      this.draw(pageNumber, RIGHT - width(pageNumber, 8.5, 'F1'), 760, {size:8.5, color:MUTED});
    });
    const objects: string[] = [];
    objects[1] = '<< /Type /Catalog /Pages 2 0 R >>';
    objects[2] = '<< /Type /Pages /Kids [' + this.pages.map((_,index) => (6 + index * 2) + ' 0 R').join(' ') + '] /Count ' + this.pages.length + ' >>';
    objects[3] = '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>';
    objects[4] = '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>';
    objects[5] = '<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>';
    this.pages.forEach((page,index) => {
      const id = 6 + index * 2, stream = page.commands.join('\n');
      objects[id] = '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ' + WIDTH + ' ' + HEIGHT + '] /Resources << /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >> >> /Contents ' + (id + 1) + ' 0 R >>';
      objects[id + 1] = '<< /Length ' + stream.length + ' >>\nstream\n' + stream + '\nendstream';
    });
    const infoId = objects.length;
    objects[infoId] = '<< /Title (Media screening report) /Creator (DeepTrace) /Subject (Advisory media screening and technical record) >>';
    let pdf = '%PDF-1.4\n%DeepTrace\n';
    const offsets = [0];
    for (let i = 1; i < objects.length; i++) {
      offsets[i] = pdf.length;
      pdf += i + ' 0 obj\n' + objects[i] + '\nendobj\n';
    }
    const xref = pdf.length;
    pdf += 'xref\n0 ' + objects.length + '\n0000000000 65535 f \n';
    for (let i = 1; i < objects.length; i++) pdf += String(offsets[i]).padStart(10, '0') + ' 00000 n \n';
    pdf += 'trailer\n<< /Size ' + objects.length + ' /Root 1 0 R /Info ' + infoId + ' 0 R >>\nstartxref\n' + xref + '\n%%EOF\n';
    return new Blob([pdf], {type:'application/pdf'});
  }
}

export function createReportPdf(report: Report): Blob {
  const doc = new ReportDocument(report);
  const result = assessment(report);
  doc.heading('1. Screening summary');
  doc.paragraph(result.title, {size:14, font:'F2', leading:19});
  doc.paragraph(result.summary, {size:11});
  if (result.missing && result.tone === 'review') doc.paragraph(result.missing + ' checks did not return a usable result.', {size:10});
  doc.paragraph(report.examination_scope, {size:10, color:MUTED});
  doc.space(3);
  doc.table(['Check', 'Finding', 'Model score', 'Coverage'], report.components.map((component,index) => [
    {text:label(component,index), font:'F2'}, outcome(component).text, number(score(component)), coverage(component,report),
  ]), [144, 90, 82, 188], true, 10);
  doc.space(6);
  doc.paragraph('Model scores are uncalibrated screening outputs, not probabilities of manipulation. No combined model score is calculated.', {size:10, color:MUTED, leading:12});

  doc.heading('2. Findings');
  const findings = report.anomalies.filter(item => !['METADATA_WARNING','MODEL_DISAGREEMENT'].includes(item.code));
  if (!findings.length) doc.paragraph('No specific findings were returned. Refer to the screening status and coverage above.', {size:10});
  findings.forEach(item => {
    const copy = observation(item.code,item.description);
    doc.ensure(42);
    doc.paragraph(copy.title, {size:10, font:'F2'});
    doc.paragraph(copy.description, {size:10}, 0);
  });

  doc.heading('3. Submitted media');
  doc.field('Filename',report.media.filename);
  doc.space(5);
  doc.facts([
    ['Media type',human(report.media.media_kind)],
    ['File size',formatBytes(report.media.size_bytes)],
    ['Duration',report.media.duration_seconds == null ? 'Not available' : number(report.media.duration_seconds,2) + ' seconds'],
  ]);

  doc.heading('4. Review and next action');
  doc.facts([
    ['Workflow',human(report.workflow_status ?? 'draft')],
    ['Report owner',report.owner || 'Not recorded'],
    ['Reviewer',report.reviewer || 'Not assigned'],
  ]);
  doc.paragraph(report.review_status, {size:10, color:MUTED});
  doc.paragraph(result.next, {size:10});
  doc.space(5);
  doc.paragraph(report.disclaimer, {size:10, color:MUTED, leading:12.5});

  doc.appendix('Appendix A. Detector evidence');
  doc.paragraph('Each detector retains its own score, decision rule, coverage, and limitations. Scores have not been combined or calibrated into an overall probability. Displayed model scores are rounded to three decimal places.', {size:10, color:MUTED});
  if (!report.components.length) doc.paragraph('No detector results were returned.');
  report.components.forEach((component,index) => {
    if (index > 0) { doc.section = 'A.' + (index + 1) + ' ' + label(component,index); doc.ensure(150); doc.space(12); }
    doc.heading('A.' + (index + 1) + ' ' + label(component,index));
    doc.facts([
      ['Detector status',human(component.status)],
      ['Model score',number(score(component))],
      ['Decision threshold',component.threshold == null ? 'Not reported' : component.threshold.toString()],
    ]);
    const validated = component.threshold_validated ?? component.threshold_validation?.validated ?? false;
    doc.field('Threshold validation',validated ? 'Validation recorded' : 'Not DPS-validated');
    doc.field('Estimated probability',component.calibrated_probability == null ? 'Not available - calibration not fitted' : number(component.calibrated_probability,4));
    doc.field('Screened coverage',coverage(component,report));
    doc.field('Model',component.detector_name ?? component.model_name);
    doc.field('Version',component.model_version,true);
    doc.field('Checkpoint',component.checkpoint,true);
    doc.field('Detector ID',component.detector_id);
    doc.field('Aggregation',component.aggregation_method);
    doc.field('Threshold source',component.threshold_source);
    if (component.threshold_validation?.dataset) doc.field('Validation dataset',component.threshold_validation.dataset);
    if (component.threshold_validation?.target_fpr != null) doc.field('Validation target FPR',number(component.threshold_validation.target_fpr,4));
    if (component.operational_status) doc.field('Operational status',human(component.operational_status));
    if (component.detector_status) doc.field('Result status',human(component.detector_status));
    if (component.thresholds) {
      doc.field('Review threshold',component.thresholds.review == null ? 'Not reported' : number(component.thresholds.review));
      doc.field('Flag threshold',component.thresholds.flag == null ? 'Not reported' : number(component.thresholds.flag));
    }
    doc.field('Flagged timestamps',component.timestamps_seconds.length ? component.timestamps_seconds.map(time).join(', ') : 'None returned');
    const notes = [...new Set([...(component.notes ?? []), ...(component.limitations ?? [])])];
    if (notes.length) { doc.heading('Processing notes and limitations',false); doc.section = 'A.' + (index + 1) + ' ' + label(component,index); doc.bullets(notes); }
    if (component.samples?.length) {
      doc.heading('Sample results (' + component.samples.length + ')',false);
      doc.section = 'A.' + (index + 1) + ' ' + label(component,index) + ' / samples';
      if (component.component === 'audio') doc.paragraph('Reported sample intervals describe the model output record; they do not establish that every instant in the interval was screened. See coverage and processing notes.', {size:10, color:MUTED});
      doc.table(['Sample', 'Reported time', 'Model score', 'Raw logits'], component.samples.map((sample,sampleIndex) => [
        String(sampleIndex + 1),
        time(sample.start_time) + (sample.end_time == null ? '' : ' - ' + time(sample.end_time)),
        {text:number(sample.raw_score),font:'F3'},
        {text:sample.raw_logits?.length ? sample.raw_logits.map(value => Number.isFinite(value) ? String(value) : 'Not available').join(', ') : 'Not reported',font:'F3'},
      ]), [48, 140, 82, 234], true, 9.5, 4.5);
    }
  });

  doc.appendix('Appendix B. Examination record');
  doc.heading('B.1 File identification');
  doc.field('Filename',report.media.filename);
  doc.field('Container',report.media.container);
  doc.field('SHA-256',report.media.sha256,true);
  doc.field('Report ID',report.report_id,true);
  doc.field('Generated',date(report.generated_at));
  if (report.analysis_id) doc.field('Workspace analysis ID',report.analysis_id,true);
  doc.heading('B.2 Recorded observations');
  if (!report.anomalies.length) doc.paragraph('None returned.');
  report.anomalies.forEach(item => {
    doc.ensure(42);
    doc.paragraph(human(item.code) + ' / ' + item.component + ' / ' + item.severity, {size:10, font:'F2'});
    doc.paragraph(item.description, {size:10});
  });
  doc.heading('B.3 Automated narrative');
  doc.paragraph(report.summary, {size:10});
  doc.field('Examination scope',report.examination_scope);
  doc.field('Review status',report.review_status);
  doc.field('Recommended action',report.recommended_action);
  doc.heading('B.4 Methods');
  if (report.methods.length) doc.bullets(report.methods); else doc.paragraph('No methods recorded.');
  doc.heading('B.5 Integrity record');
  const integrity = Object.entries(report.integrity);
  if (integrity.length) integrity.forEach(([key,value]) => doc.field(human(key),value));
  else doc.paragraph('No additional integrity fields were returned.');
  if (report.processing) {
    doc.heading('Processing record',false);
    Object.entries(report.processing).forEach(([key,value]) => doc.field(human(key),value));
  }
  doc.heading('B.6 Limitations');
  doc.paragraph(report.disclaimer, {size:10});
  doc.bullets(report.limitations);
  doc.heading('B.7 Reporting references');
  if (!report.references.length) doc.paragraph('No references recorded.');
  report.references.forEach(reference => {
    doc.ensure(45);
    doc.paragraph(reference.organization + ' / ' + reference.title, {size:10, font:'F2'});
    doc.paragraph(reference.version, {size:10, color:MUTED});
    doc.paragraph(reference.application, {size:10});
    doc.paragraph(reference.url, {size:10, color:MUTED});
    doc.space(4);
  });
  if (report.review_checks?.length) {
    doc.appendix('Appendix C. Supplementary analysis');
    doc.paragraph('These descriptive measurements support review. They do not identify a manipulation technique, establish authenticity, or change the detector scores.');
    report.review_checks.forEach((check,index) => {
      doc.heading('C.' + (index+1) + ' ' + check.title);
      doc.field('Status',human(check.status));
      doc.field('Method',check.method);
      doc.field('Method version',check.version);
      doc.paragraph(check.summary);
      doc.facts(Object.entries(check.measurements).filter(([,value]) => typeof value === 'number').map(([key,value]) => [human(key),Number(Number(value).toFixed(4)).toString()]));
      Object.entries(check.measurements).filter(([,value]) => typeof value !== 'number').forEach(([key,value]) => doc.field(human(key),value));
      if (check.intervals.length) doc.table(['Start', 'End', 'Measurement'],check.intervals.map(item => [
        typeof item.start_time === 'number' ? time(item.start_time) : 'Not reported',
        typeof item.end_time === 'number' ? time(item.end_time) : 'Not reported',
        Object.entries(item).filter(([key]) => !['start_time','end_time'].includes(key)).map(([key,value]) => human(key) + ': ' + (typeof value === 'number' ? number(value,4) : String(value))).join('; '),
      ]),[65,65,374],true,9.5,5);
      doc.bullets(check.limitations);
    });
  }
  return doc.blob();
}
