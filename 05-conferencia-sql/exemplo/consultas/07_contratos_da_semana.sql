-- Quadro "Contratos da semana": pagos nos 7 dias antes de :agora.
SELECT id,
       proposta_id,
       pago_em,
       valor_liberado
FROM contratos
WHERE pago_em >= datetime(:agora, '-7 days')
ORDER BY pago_em DESC;
