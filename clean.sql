delete from weather_report
where time < now() - interval '14 days'

