import json
from browser_util import wait_until


def check_progress(page):
    importing=dict(running=True,label='Lichess games',done=40,total=0)
    indexing=dict(running=True,collection='My games',done=25,total=100,errors=0)
    page.route('**/api/import/status',lambda route:route.fulfill(json=json.loads(json.dumps(importing))))
    page.route('**/api/study/index',lambda route:route.fulfill(json=json.loads(json.dumps(indexing))))
    try:
        page.evaluate("JobProgress.begin('import','Lichess games')")
        page.get_by_text('40 games processed · Still receiving games; total not yet known.',exact=True).wait_for()
        assert not page.locator('[data-job=import] progress').is_visible()
        importing.update(done=50,total=100)
        wait_until(page,"()=>document.querySelector('[data-job=import] progress')?.value===50")
        page.evaluate("async()=>{await Caissa.api('study/index',{collection:1});await Caissa.go('studies');}")
        assert page.locator('[data-job=index] progress').get_attribute('max')=='100'
        wait_until(page,"()=>document.querySelector('[data-job=index] progress')?.value===25")
        page.evaluate("Caissa.go('database')")
        assert page.locator('[data-job=index]').is_visible()
        indexing.update(done=75)
        wait_until(page,"()=>document.querySelector('[data-job=index] progress')?.value===75")
        indexing.update(done=100,running=False)
        page.get_by_text('Indexing complete · My games',exact=True).wait_for()
        assert page.locator('[data-job=index] progress').evaluate('(el)=>el.value')==100
        page.evaluate("JobProgress.end('import',{added:90,duplicates:10,skipped:0})")
        page.get_by_text('90 added · 10 duplicates',exact=True).wait_for()
        assert page.locator('[data-job=import] progress').evaluate('(el)=>el.value')==100
        page.evaluate("JobProgress.begin('index','Bad collection');JobProgress.end('index',null,new Error('Cannot read collection'))")
        page.get_by_text('Cannot read collection',exact=True).wait_for()
        assert not page.locator('[data-job=index] progress').is_visible()
        while page.get_by_role('button',name='Dismiss task notification').count():
            page.get_by_role('button',name='Dismiss task notification').first.click()
        assert page.locator('.job-progress-card').count()==0
    finally:
        page.unroute('**/api/import/status')
        page.unroute('**/api/study/index')
