{{/*
Common labels applied to every resource in this chart.
*/}}
{{- define "water-meter.labels" -}}
app.kubernetes.io/name: water-meter
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}
