"""Check independent report dispatch, RMS propagation and failed output recovery."""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from docx import Document

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from reporting import render_saved, standard_reports


def custom_writer(directory, summary, sections, *, marker):
    standard_reports(directory,summary,sections)
    path=directory/"report.docx"
    doc=Document(path); doc.add_paragraph(marker); doc.save(path)


def incomplete_writer(directory, summary, sections):
    Document().save(directory/"report.docx")


def check(source):
    with TemporaryDirectory() as temp:
        here=Path(temp)
        from shutil import copytree
        case=here/"source"
        copytree(source,case)
        summary=case/"summary.json"
        data=json.loads(summary.read_bytes())
        wall=next(w for w in data["walls"] if w["whole"].get("rms_mm") is not None)
        # This display-only fixture distinguishes imported measurements from a recomputation.
        wall["whole"]["rms_mm"]=12.345
        data["algorithms"]["stages"]["rms"]["call"]="fixture:recorded_rms"
        summary.write_text(json.dumps(data),encoding="utf8")
        before=summary.read_bytes()
        profile=here/"writer.json"
        profile.write_text(json.dumps({"api_version":1,"stages":{"rms":{"call":"missing_module:never_loaded"}},
                                       "report":{"call":"__main__:custom_writer","options":{"marker":"Custom writer verified"}}}),encoding="utf8")
        out=here/"rendered"
        render_saved(case,out,str(profile))
        report=Document(out/"report.docx")
        cells={c.text for t in report.tables for row in t.rows for c in row.cells}
        assert "12.345" in cells and "fixture:recorded_rms" in cells
        assert "12.345" in (out/"report.html").read_text(encoding="utf8")
        assert any(p.text=="Custom writer verified" for p in report.paragraphs)
        manifest=json.loads((out/"report_manifest.json").read_bytes())
        assert manifest["writer"]["call"]=="__main__:custom_writer" and manifest["rms"]["call"]=="fixture:recorded_rms"
        assert summary.read_bytes()==before==(out/"summary.json").read_bytes()
        if "group09_review" in data:
            from group09_report import load_review
            record,files=load_review(case,data)
            assert manifest["group09_review"]==data["group09_review"]
            assert record==load_review(out,data)[0]
            for file in files:
                original=file.read_bytes()
                if file.suffix==".npz":
                    import numpy as np
                    np.savez_compressed(file,source_rows=[0])
                else:
                    file.write_bytes(original+b" ")
                damaged=here/"damaged"
                try: render_saved(case,damaged)
                except ValueError: pass
                else: raise AssertionError("A changed paired dependency was accepted")
                assert not damaged.exists()
                file.write_bytes(original)
        profile.write_text('{"api_version":1,"report":{"call":"__main__:incomplete_writer"}}',encoding="utf8")
        failed=here/"failed"
        try: render_saved(case,failed,str(profile))
        except (OSError,ValueError): pass
        else: raise AssertionError("A missing HTML output must fail")
        assert not failed.exists() and summary.read_bytes()==before
        if "preprocessing" in data:
            sections=case/data["window_sections_file"]
            original=sections.read_bytes()
            sections.write_bytes(original+b"\n")
            try: render_saved(case,failed)
            except ValueError as error: assert "preprocessing selection" in str(error)
            else: raise AssertionError("A changed window file must fail")
            assert not failed.exists()
            sections.write_bytes(original)
            mapping=data["preprocessing"]["source_rows_file"]
            if mapping:
                assert (out/mapping).read_bytes()==(case/mapping).read_bytes()
                import numpy as np
                with np.load(case/mapping) as archive:
                    indices=archive["source_rows"].copy()
                indices[0]+=1
                np.savez_compressed(case/mapping,source_rows=indices)
                try: render_saved(case,failed)
                except ValueError as error: assert "row map" in str(error)
                else: raise AssertionError("A changed source row map must fail")
                assert not failed.exists()
            del data["preprocessing"],data["window_sections_sha256"]
            data.pop("group09_review",None)
            summary.write_text(json.dumps(data),encoding="utf8")
            legacy=here/"historical"
            render_saved(case,legacy)
            assert any("not recorded" in p.text for p in Document(legacy/"report.docx").paragraphs)
            assert "Input preprocessing was not recorded" in (legacy/"report.html").read_text(encoding="utf8")
        print("Independent RMS and report selection, saved values in Word/HTML, input preservation and partial-failure recovery passed.")


if __name__=="__main__":
    if len(sys.argv)!=2:
        raise SystemExit("Usage: python tests/check_reporting.py RESULT_DIRECTORY")
    check(Path(sys.argv[1]))
