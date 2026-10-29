from xml.etree import ElementTree as ET


def make_score(n=12, transposed=True, complex_source=False, repeat=False, second_source=True, target_multivoice=False):
    root = ET.Element('museScore', version='4.20')
    score = ET.SubElement(root, 'Score')
    ET.SubElement(score, 'metaTag', name='workTitle').text = 'Cue Test Suite'
    voices = [('1','Oboe',0,0), ('2','Clarinet in B♭',-2 if transposed else 0,-1 if transposed else 0)]
    if second_source:
        voices += [('3','Flute',0,0)]
    for sid, name, chrom, dia in voices:
        part = ET.SubElement(score, 'Part')
        ET.SubElement(part, 'Staff', id=sid)
        ET.SubElement(part, 'trackName').text = name
        inst = ET.SubElement(part, 'Instrument')
        ET.SubElement(inst, 'transposeChromatic').text = str(chrom)
        ET.SubElement(inst, 'transposeDiatonic').text = str(dia)
    for sid, _, _, _ in voices:
        staff = ET.SubElement(score, 'Staff', id=sid)
        for i in range(n):
            bar = ET.SubElement(staff, 'Measure', number=str(i+1))
            voice = ET.SubElement(bar, 'voice')
            if i == 0:
                ts = ET.SubElement(voice, 'TimeSig')
                ET.SubElement(ts, 'sigN').text = '4'
                ET.SubElement(ts, 'sigD').text = '4'
            if repeat and i == n-3:
                ET.SubElement(voice, 'startRepeat')
            if sid in ('1','3'):
                for j in range(4):
                    chord = ET.SubElement(voice, 'Chord')
                    ET.SubElement(chord, 'durationType').text = 'quarter'
                    if complex_source and sid == '1' and i == n-2:
                        ET.SubElement(chord, 'Tuplet')
                    note = ET.SubElement(chord, 'Note')
                    ET.SubElement(note, 'pitch').text = str(60 + (j if sid == '1' else 2*j))
                    ET.SubElement(note, 'tpc').text = '14'
            elif i == n-1:
                chord = ET.SubElement(voice,'Chord')
                ET.SubElement(chord, 'durationType').text = 'whole'
                note = ET.SubElement(chord,'Note')
                ET.SubElement(note, 'pitch').text = '60'
                ET.SubElement(note, 'tpc').text = '14'
            else:
                rest = ET.SubElement(voice, 'Rest')
                ET.SubElement(rest, 'durationType').text = 'measure'
                if target_multivoice and i == n-3:
                    extra = ET.SubElement(bar, 'voice')
                    r = ET.SubElement(extra, 'Rest')
                    ET.SubElement(r, 'durationType').text = 'measure'
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)
