{{- define "gateway.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- define "gateway.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "gateway.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- define "gateway.image" -}}
{{- printf "%s@%s" .repository .digest -}}
{{- end -}}
{{- define "gateway.validateTraffic" -}}
{{- if ne (add .Values.traffic.stableWeight .Values.traffic.canaryWeight) 100 -}}
{{- fail "traffic weights must sum to100" -}}
{{- end -}}
{{- end -}}
