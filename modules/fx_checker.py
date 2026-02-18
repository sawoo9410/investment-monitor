"""환율 체크 및 구간 판단 모듈"""
from typing import Dict, Optional

def check_fx_zone(current_rate: float, config: Dict) -> Dict:
    """환율 구간 판단"""
    zones = config['fx_rules']['zones']
    baseline = config['fx_rules']['baseline']
    
    # 구간 판단
    if current_rate <= zones['bulk_convert']:
        zone = "bulk_convert"
        zone_name = "쌓인 원화 50% 한방 환전"
        action = f"쌓인 원화의 50%를 환전하세요"
    elif current_rate <= zones['full_convert']:
        zone = "full_convert"
        zone_name = "전액 환전 구간"
        action = "80만원 전액 환전"
    elif current_rate <= zones['normal_end']:
        zone = "normal"
        zone_name = "정상 구간"
        action = "40만원 환전 (정상)"
    elif current_rate <= zones['full_pause']:
        zone = "half_pause"
        zone_name = "환전 보류 구간"
        action = "환전 보류, 원화 현금 적립"
    else:
        zone = "full_pause"
        zone_name = "전액 보류 구간"
        action = "전액 원화 보유"
    
    return {
        'current_rate': current_rate,
        'baseline': baseline,
        'zone': zone,
        'zone_name': zone_name,
        'action': action,
        'diff_from_baseline': round(current_rate - baseline, 2)
    }

def detect_fx_zone_change(prev_rate: float, current_rate: float, config: Dict) -> Optional[Dict]:
    """환율 구간 변경 감지 (텔레그램 알림용)"""
    prev_zone = check_fx_zone(prev_rate, config)
    current_zone = check_fx_zone(current_rate, config)
    
    if prev_zone['zone'] != current_zone['zone']:
        return {
            'changed': True,
            'prev_zone': prev_zone['zone_name'],
            'current_zone': current_zone['zone_name'],
            'current_rate': current_rate,
            'action': current_zone['action']
        }
    
    return {'changed': False}