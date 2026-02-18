"""환율 구간 체크 및 변경 감지 모듈"""
from typing import Dict, Optional

def check_fx_zone(fx_rate: float, fx_rules: Dict) -> Dict:
    """현재 환율이 어느 구간에 속하는지 판단"""
    zones = fx_rules['zones']
    baseline = fx_rules['baseline']
    
    # 구간 판단
    if fx_rate <= zones['bulk_convert']:
        zone = 'bulk_convert'
        zone_name = '쌓인 원화 50% 한방 환전'
        action = '쌓인 원화의 50%를 환전하세요'
    elif fx_rate <= zones['full_convert']:
        zone = 'full_convert'
        zone_name = '전액 환전 구간'
        action = '80만원 전액 환전'
    elif fx_rate <= zones['normal_end']:
        zone = 'normal'
        zone_name = '정상 구간'
        action = '40만원 환전 (정상)'
    elif fx_rate <= zones['full_pause']:
        zone = 'half_pause'
        zone_name = '환전 보류 구간'
        action = '환전 보류, 원화 현금 적립'
    else:
        zone = 'full_pause'
        zone_name = '전액 보류 구간'
        action = '전액 원화 보유'
    
    return {
        'zone': zone,
        'zone_name': zone_name,
        'action': action,
        'baseline': baseline,
        'current_rate': fx_rate
    }

def detect_fx_zone_change(prev_rate: float, current_rate: float, fx_rules: Dict) -> Optional[Dict]:
    """환율 구간 변경 감지"""
    prev_zone_info = check_fx_zone(prev_rate, fx_rules)
    current_zone_info = check_fx_zone(current_rate, fx_rules)
    
    if prev_zone_info['zone'] != current_zone_info['zone']:
        return {
            'prev_zone': prev_zone_info['zone_name'],
            'current_zone': current_zone_info['zone_name'],
            'prev_rate': prev_rate,
            'current_rate': current_rate,
            'action': current_zone_info['action']
        }
    
    return None