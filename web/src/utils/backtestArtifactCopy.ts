import type { BacktestArtifactEntry, BacktestArtifactSummaryItem } from '../types/backtests'

type SidecarCopySource = (BacktestArtifactEntry | BacktestArtifactSummaryItem) & { path?: string }

type SidecarSnippetSpec = {
  modelName: string
  loader: 'parquet' | 'json'
}

const SIDE_CAR_SNIPPETS: Partial<Record<string, SidecarSnippetSpec>> = {
  candidates_json: { modelName: 'CandidateRecord', loader: 'json' },
  candidates_parquet: { modelName: 'CandidateRecord', loader: 'parquet' },
  equity_parquet: { modelName: 'EquityPoint', loader: 'parquet' },
  features_parquet: { modelName: 'FeatureSnapshotRecord', loader: 'parquet' },
  labels_parquet: { modelName: 'OutcomeLabelRecord', loader: 'parquet' },
  orders_parquet: { modelName: 'OrderRecord', loader: 'parquet' },
  rejections_parquet: { modelName: 'RejectionRecord', loader: 'parquet' },
  report_parquet: { modelName: 'ReportSummaryRecord', loader: 'parquet' },
  trades_parquet: { modelName: 'TradeRecord', loader: 'parquet' },
}

function escapePythonString(value: string): string {
  return value.replaceAll('\\', '\\\\').replaceAll('"', '\\"')
}

function pythonStringLiteral(value: string): string {
  return `"${escapePythonString(value)}"`
}

function artifactPathLiteral(artifact: SidecarCopySource): string {
  const path = 'path' in artifact ? artifact.path : undefined
  if (path) {
    return pythonStringLiteral(path)
  }

  const placeholder =
    artifact.format === 'parquet'
      ? `/path/to/${artifact.kind}.parquet`
      : artifact.format === 'json'
        ? `/path/to/${artifact.kind}.json`
        : artifact.format === 'yaml'
          ? `/path/to/${artifact.kind}.yaml`
          : `/path/to/${artifact.kind}.txt`
  return pythonStringLiteral(placeholder)
}

function buildFieldGuideHelper(): string[] {
  return [
    'def format_annotation(annotation: object) -> str:',
    '    text = str(annotation).replace("typing.", "")',
    '    return text.replace("<class \'", "").replace("\'>", "")',
    '',
    'def explain_record(model_cls: type[BaseModel], record: BaseModel) -> None:',
    '    print(f"Field guide for {model_cls.__name__}:")',
    '    for field_name, field in model_cls.model_fields.items():',
    '        value = getattr(record, field_name)',
    '        meaning = field.description or field_name.replace("_", " ")',
    '        if field.is_required():',
    '            state = "required"',
    '        elif field.default_factory is not None:',
    '            state = "defaulted (factory)"',
    '        else:',
    '            state = f"defaulted ({field.default!r})"',
    '        print(f"- {field_name} represents {meaning}")',
    '        print(f"  type={format_annotation(field.annotation)}; {state}; value={value!r}")',
    '',
  ]
}

function buildParquetSnippet(modelName: string, pathLiteral: string): string[] {
  return [
    'import pandas as pd',
    `from app.output.records import ${modelName}`,
    '',
    `artifact_path = Path(${pathLiteral})`,
    '',
    'frame = pd.read_parquet(artifact_path)',
    'if frame.empty:',
    '    raise ValueError(f"{artifact_path} is empty")',
    '',
    'row_data = frame.iloc[0].to_dict()',
    `record = ${modelName}.model_validate(row_data)`,
    'print(record)',
    'print(record.model_dump())',
    'print()',
    ...buildFieldGuideHelper(),
    `explain_record(${modelName}, record)`,
  ]
}

function buildJsonSnippet(modelName: string, pathLiteral: string): string[] {
  return [
    'import json',
    `from app.output.models import ${modelName}`,
    '',
    `artifact_path = Path(${pathLiteral})`,
    '',
    'payload = json.loads(artifact_path.read_text())',
    'if isinstance(payload, list):',
    '    if not payload:',
    '        raise ValueError(f"{artifact_path} is empty")',
    '    row_data = payload[0]',
    'elif isinstance(payload, dict):',
    '    row_data = payload',
    'else:',
    '    raise TypeError(f"Expected list or dict payload in {artifact_path}")',
    '',
    `record = ${modelName}.model_validate(row_data)`,
    'print(record)',
    'print(record.model_dump())',
    'print()',
    ...buildFieldGuideHelper(),
    `explain_record(${modelName}, record)`,
  ]
}

function buildFallbackSnippet(pathLiteral: string): string[] {
  return [
    'print("This artifact is not yet wired to a Pydantic record model.")',
    `artifact_path = Path(${pathLiteral})`,
    'print(artifact_path.read_text()[:4000])',
  ]
}

export function buildSidecarCopySnippet(artifact: SidecarCopySource): string {
  const pathLiteral = artifactPathLiteral(artifact)
  const spec = SIDE_CAR_SNIPPETS[artifact.kind]

  const lines: string[] = ['from pathlib import Path', 'from pydantic import BaseModel', '']

  if (!spec) {
    lines.push(...buildFallbackSnippet(pathLiteral))
    return lines.join('\n')
  }

  lines.push(
    ...(spec.loader === 'parquet'
      ? buildParquetSnippet(spec.modelName, pathLiteral)
      : buildJsonSnippet(spec.modelName, pathLiteral)),
  )
  return lines.join('\n')
}
